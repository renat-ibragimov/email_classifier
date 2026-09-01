import json
import logging
from functools import lru_cache

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionNamedToolChoiceParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolParam,
    ChatCompletionUserMessageParam,
)

from app.config import settings
from app.helpers.dto import ClassificationResult, ParsedEmail
from app.helpers.enums import EmailCategoryEnum, LanguageEnum

logger = logging.getLogger(__name__)

UKRAINIAN_HINT = " Written in Ukrainian."

# Share of alphabetic characters that must be Cyrillic for the text to pass as Ukrainian.
CYRILLIC_MIN_RATIO = 0.5
CYRILLIC_RANGE = ("\u0400", "\u04ff")  # Cyrillic block; includes the Ukrainian-only letters

RETRY_USER_LINE = "Respond in Ukrainian only."

SYSTEM_PROMPT = (
    "You are an email security classifier. "
    "Analyze the provided email and classify it using the classify_email tool. "
    "Consider sender domain, subject line, body content, links, "
    "urgency language, and requests for sensitive information."
)

REVIEW_PROMPT = (
    "You are a senior email security analyst performing a second review. "
    "The initial classification was uncertain. Be extra critical. "
    "Look for subtle signs of spam and phishing: "
    "affiliate/referral links disguised as personal recommendations, "
    "product promotions embedded in casual conversation, "
    "password reset links from external domains mimicking internal IT, "
    "urgency disguised as routine maintenance deadlines. "
    "Classify the email using the classify_email tool."
)

# Leads the system prompt rather than trailing it: models weigh the opening
# sentence far more reliably than an instruction buried after the task.
UKRAINIAN_INSTRUCTION = (
    "WRITE YOUR ANSWER IN UKRAINIAN. "
    "The `reasoning` field and every item of the `signals` array MUST be written in Ukrainian, "
    "never in English or any other language. "
    "The `category` value is the only exception: it stays one of the English enum values "
    "listed in the tool schema. "
)


def build_classify_tool(language: LanguageEnum) -> ChatCompletionToolParam:
    """Build the classify_email tool schema for the requested output language.

    The schema is rebuilt per request so the Ukrainian requirement is repeated in
    the field descriptions the model reads while filling the tool call in.

    Args:
        language: Language the LLM-written fields should be produced in.

    Returns:
        Tool parameter with language-specific field descriptions.

    """
    hint = UKRAINIAN_HINT if language is LanguageEnum.UK else ""

    return ChatCompletionToolParam(
        type="function",
        function={
            "name": "classify_email",
            "description": "Classify an email into a category with confidence score, reasoning, and signals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [e.value for e in EmailCategoryEnum],
                        "description": "Email category.",
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Confidence score from 0.0 to 1.0.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Explanation of why this category was chosen." + hint,
                    },
                    "signals": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "description": "A signal supporting the classification." + hint,
                        },
                        "description": "Specific signals in the email that support the classification.",
                    },
                },
                "required": ["category", "confidence", "reasoning", "signals"],
            },
        },
    )


@lru_cache(maxsize=1)
def get_client() -> AsyncOpenAI:
    """Return the shared OpenAI client, creating it on first use.

    The client owns an HTTP connection pool, so it is built once and reused
    across requests instead of being re-created on every classification call.

    Returns:
        Cached AsyncOpenAI client.

    """
    return AsyncOpenAI(api_key=settings.openai_api_key)


def cyrillic_ratio(text: str) -> float:
    """Return the share of alphabetic characters in text that are Cyrillic.

    Args:
        text: Text to measure.

    Returns:
        Ratio from 0.0 to 1.0; 0.0 when the text has no alphabetic characters.

    """
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0

    low, high = CYRILLIC_RANGE
    cyrillic = sum(1 for char in letters if low <= char <= high)
    return cyrillic / len(letters)


def is_ukrainian(text: str) -> bool:
    """Check whether text reads as Ukrainian rather than English.

    A ratio test on the alphabet is enough here: the alternative the model falls
    back to is English, so any Latin-heavy answer is a miss.

    Args:
        text: Text to check.

    Returns:
        True if at least CYRILLIC_MIN_RATIO of its letters are Cyrillic.

    """
    return cyrillic_ratio(text) >= CYRILLIC_MIN_RATIO


def _system_prompt(base_prompt: str, language: LanguageEnum) -> str:
    """Return the system prompt adjusted for the requested output language.

    Args:
        base_prompt: Prompt for the pass being run (first or review).
        language: Language the LLM-written fields should be produced in.

    Returns:
        The prompt as-is for English, or led by the Ukrainian instruction.

    """
    if language is LanguageEnum.UK:
        return UKRAINIAN_INSTRUCTION + base_prompt
    return base_prompt


def _build_user_message(email: ParsedEmail) -> str:
    """Build user message from parsed email data.

    Args:
        email: Parsed email DTO.

    Returns:
        Formatted string with email headers and body.

    """
    return f"From: {email.sender}\nTo: {email.to}\nSubject: {email.subject}\nDate: {email.date}\n\n{email.body}"


async def _call_openai(user_message: str, system_prompt: str, language: LanguageEnum) -> dict:
    """Make a single classification call to OpenAI with tool use.

    Args:
        user_message: Formatted email content.
        system_prompt: System prompt for the LLM.
        language: Language the tool schema is built for.

    Returns:
        Parsed tool call arguments as dict.

    Raises:
        RuntimeError: If the model does not return a tool call.

    """
    response = await get_client().chat.completions.create(
        model=settings.openai_model,
        messages=[
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
            ChatCompletionUserMessageParam(role="user", content=user_message),
        ],
        tools=[build_classify_tool(language)],
        tool_choice=ChatCompletionNamedToolChoiceParam(
            type="function",
            function={"name": "classify_email"},
        ),
    )

    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        raise RuntimeError("LLM did not return a tool call")

    return json.loads(tool_calls[0].function.arguments)


async def _call_in_language(user_message: str, system_prompt: str, language: LanguageEnum) -> dict:
    """Run one classification pass, retrying once if the answer ignored the language.

    A miss is not an error: a stray English reasoning is still a usable
    classification, so the second answer is returned either way and only logged
    when it fails too.

    Args:
        user_message: Formatted email content.
        system_prompt: System prompt for the pass being run.
        language: Language the LLM-written fields should be produced in.

    Returns:
        Parsed tool call arguments as dict.

    """
    result = await _call_openai(user_message, system_prompt, language)

    if language is not LanguageEnum.UK or is_ukrainian(result.get("reasoning", "")):
        return result

    logger.warning("LLM answered in the wrong language; retrying once with an explicit instruction")
    result = await _call_openai(f"{user_message}\n\n{RETRY_USER_LINE}", system_prompt, language)

    if not is_ukrainian(result.get("reasoning", "")):
        logger.warning("LLM still did not answer in Ukrainian after the retry; keeping the response as-is")

    return result


async def classify_email(
    parsed_email: ParsedEmail,
    language: LanguageEnum = LanguageEnum.EN,
) -> ClassificationResult:
    """Classify an email using OpenAI tool use.

    Performs a second pass with stricter analysis if confidence is below threshold.

    Args:
        parsed_email: Parsed email DTO.
        language: Language for the reasoning and signals; the category stays English.

    Returns:
        ClassificationResult with category, confidence, reasoning, signals, reviewed.

    """
    user_message = _build_user_message(parsed_email)

    result = await _call_in_language(user_message, _system_prompt(SYSTEM_PROMPT, language), language)
    reviewed = False

    if result.get("confidence", 0) <= settings.confidence_threshold:
        result = await _call_in_language(user_message, _system_prompt(REVIEW_PROMPT, language), language)
        reviewed = True

    return ClassificationResult(
        category=EmailCategoryEnum(result.get("category", "")),
        confidence=result.get("confidence", 0.0),
        reasoning=result.get("reasoning", ""),
        signals=result.get("signals", []),
        reviewed=reviewed,
    )
