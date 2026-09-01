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

# Substrings that force the second-pass review regardless of first-pass confidence.
# Matched case-insensitively against subject + body. Kept deliberately small and
# blunt: the point is to spend a second call on the topics where a confidently
# wrong "personal" or "transactional" verdict is most expensive.
HIGH_RISK_CUES = (
    "password",
    "passcode",
    "verify your account",
    "login",
    "sign in",
    "portal",
    "reset",
    "update your",
    "deadline",
    "expires",
    "urgent",
    "immediately",
    "suspended",
)

CLASSIFY_TOOL = ChatCompletionToolParam(
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
                    "description": "Explanation of why this category was chosen.",
                },
                "signals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific signals in the email that support the classification.",
                },
            },
            "required": ["category", "confidence", "reasoning", "signals"],
        },
    },
)

TRANSLATE_TOOL = ChatCompletionToolParam(
    type="function",
    function={
        "name": "translate_result",
        "description": "Return the Ukrainian translation of a classification reasoning and its signals.",
        "parameters": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "The reasoning translated into Ukrainian.",
                },
                "signals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "The signals translated into Ukrainian, same count and same order as the input.",
                },
            },
            "required": ["reasoning", "signals"],
        },
    },
)

SYSTEM_PROMPT = (
    "You are an email security classifier. "
    "Analyze the provided email and classify it using the classify_email tool. "
    "Consider sender domain, subject line, body content, links, "
    "urgency language, and requests for sensitive information."
)

REVIEW_PROMPT = (
    "You are a senior email security analyst performing a second review. "
    "Be extra critical. "
    "Look for subtle signs of spam and phishing: "
    "affiliate/referral links disguised as personal recommendations, "
    "product promotions embedded in casual conversation, "
    "password reset links from external domains mimicking internal IT, "
    "urgency disguised as routine maintenance deadlines. "
    "If the email mentions credentials, logins, account verification, portals, or deadlines, "
    "actively challenge any benign verdict: state what would have to be true for it to be safe, "
    "and only keep a benign category once that holds. "
    "Classify the email using the classify_email tool."
)

TRANSLATE_PROMPT = (
    "You are a professional translator working on email security reports. "
    "Translate the reasoning and every signal into Ukrainian using the translate_result tool. "
    "Write natural, professional Ukrainian. "
    "Leave technical terms, product names, domain names, URLs, email addresses and header names "
    "exactly as they are — do not transliterate or translate them. "
    "Return exactly as many signals as you were given, in the same order, one translation per signal."
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


def has_high_risk_cues(email: ParsedEmail) -> bool:
    """Check whether the email touches a topic that always deserves a second opinion.

    Args:
        email: Parsed email DTO.

    Returns:
        True if subject or body contains any HIGH_RISK_CUES substring.

    """
    haystack = f"{email.subject}\n{email.body}".lower()
    return any(cue in haystack for cue in HIGH_RISK_CUES)


def _build_user_message(email: ParsedEmail) -> str:
    """Build user message from parsed email data.

    Args:
        email: Parsed email DTO.

    Returns:
        Formatted string with email headers and body.

    """
    return f"From: {email.sender}\nTo: {email.to}\nSubject: {email.subject}\nDate: {email.date}\n\n{email.body}"


async def _call_tool(user_message: str, system_prompt: str, tool: ChatCompletionToolParam) -> dict:
    """Make a single forced-tool-use call to OpenAI.

    Args:
        user_message: User-role content for the call.
        system_prompt: System prompt for the call.
        tool: Tool the model is forced to call.

    Returns:
        Parsed tool call arguments as dict.

    Raises:
        RuntimeError: If the model does not return a tool call.

    """
    response = await get_client().chat.completions.create(
        model=settings.openai_model,
        temperature=0,
        messages=[
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
            ChatCompletionUserMessageParam(role="user", content=user_message),
        ],
        tools=[tool],
        tool_choice=ChatCompletionNamedToolChoiceParam(
            type="function",
            function={"name": tool["function"]["name"]},
        ),
    )

    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        raise RuntimeError("LLM did not return a tool call")

    return json.loads(tool_calls[0].function.arguments)


async def _call_openai(user_message: str, system_prompt: str) -> dict:
    """Make a single classification call to OpenAI with tool use.

    Args:
        user_message: Formatted email content.
        system_prompt: System prompt for the LLM.

    Returns:
        Parsed tool call arguments as dict.

    """
    return await _call_tool(user_message, system_prompt, CLASSIFY_TOOL)


async def translate_result(reasoning: str, signals: list[str]) -> tuple[str, list[str]]:
    """Translate an English classification result into Ukrainian.

    Runs after the analysis is final, so a translation problem can never change
    the verdict: any failure returns the English text untouched.

    Args:
        reasoning: English reasoning from the analysis.
        signals: English signals from the analysis.

    Returns:
        Tuple of (reasoning, signals) in Ukrainian, or the English input if the
        call failed or came back in a shape that does not match the input.

    """
    if not reasoning and not signals:
        return reasoning, signals

    payload = json.dumps({"reasoning": reasoning, "signals": signals}, ensure_ascii=False)

    # Deliberately broad: a failed translation must never fail the classification.
    try:
        translated = await _call_tool(payload, TRANSLATE_PROMPT, TRANSLATE_TOOL)
    except Exception:
        logger.warning("Translation call failed; keeping the English text", exc_info=True)
        return reasoning, signals

    translated_reasoning = translated.get("reasoning") or ""
    translated_signals = translated.get("signals") or []

    if not translated_reasoning or len(translated_signals) != len(signals):
        logger.warning("Translation did not match the source shape; keeping the English text")
        return reasoning, signals

    return translated_reasoning, translated_signals


async def classify_email(
    parsed_email: ParsedEmail,
    language: LanguageEnum = LanguageEnum.EN,
) -> ClassificationResult:
    """Classify an email using OpenAI tool use.

    The analysis always runs in English so the verdict does not depend on the
    requested output language; Ukrainian output is a separate translation step
    applied to the finished result.

    A second, stricter pass runs when the first pass is not confident, and
    unconditionally when the email touches a high-risk topic.

    Args:
        parsed_email: Parsed email DTO.
        language: Language for the reasoning and signals; the category stays English.

    Returns:
        ClassificationResult with category, confidence, reasoning, signals, reviewed.

    """
    user_message = _build_user_message(parsed_email)

    result = await _call_openai(user_message, SYSTEM_PROMPT)
    reviewed = False

    low_confidence = result.get("confidence", 0) <= settings.confidence_threshold
    if low_confidence or has_high_risk_cues(parsed_email):
        result = await _call_openai(user_message, REVIEW_PROMPT)
        reviewed = True

    reasoning = result.get("reasoning", "")
    signals = result.get("signals", [])

    if language is LanguageEnum.UK:
        reasoning, signals = await translate_result(reasoning, signals)

    return ClassificationResult(
        category=EmailCategoryEnum(result.get("category", "")),
        confidence=result.get("confidence", 0.0),
        reasoning=reasoning,
        signals=signals,
        reviewed=reviewed,
    )
