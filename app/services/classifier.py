import json

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionNamedToolChoiceParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolParam,
    ChatCompletionUserMessageParam,
)

from app.config import settings
from app.helpers.dto import ClassificationResult, ParsedEmail
from app.helpers.enums import EmailCategoryEnum

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


def _build_user_message(email: ParsedEmail) -> str:
    """Build user message from parsed email data.

    Args:
        email: Parsed email DTO.

    Returns:
        Formatted string with email headers and body.

    """
    return (
        f"From: {email.sender}\n"
        f"To: {email.to}\n"
        f"Subject: {email.subject}\n"
        f"Date: {email.date}\n\n"
        f"{email.body}"
    )


async def _call_openai(user_message: str, system_prompt: str) -> dict:
    """Make a single classification call to OpenAI with tool use.

    Args:
        user_message: Formatted email content.
        system_prompt: System prompt for the LLM.

    Returns:
        Parsed tool call arguments as dict.

    Raises:
        RuntimeError: If the model does not return a tool call.

    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
            ChatCompletionUserMessageParam(role="user", content=user_message),
        ],
        tools=[CLASSIFY_TOOL],
        tool_choice=ChatCompletionNamedToolChoiceParam(
            type="function",
            function={"name": "classify_email"},
        ),
    )

    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        raise RuntimeError("LLM did not return a tool call")

    return json.loads(tool_calls[0].function.arguments)


async def classify_email(parsed_email: ParsedEmail) -> ClassificationResult:
    """Classify an email using OpenAI tool use.

    Performs a second pass with stricter analysis if confidence is below threshold.

    Args:
        parsed_email: Parsed email DTO.

    Returns:
        ClassificationResult with category, confidence, reasoning, signals, reviewed.

    """
    user_message = _build_user_message(parsed_email)

    result = await _call_openai(user_message, SYSTEM_PROMPT)
    reviewed = False

    if result.get("confidence", 0) <= settings.confidence_threshold:
        result = await _call_openai(user_message, REVIEW_PROMPT)
        reviewed = True

    return ClassificationResult(
        category=EmailCategoryEnum(result.get("category", "")),
        confidence=result.get("confidence", 0.0),
        reasoning=result.get("reasoning", ""),
        signals=result.get("signals", []),
        reviewed=reviewed,
    )
