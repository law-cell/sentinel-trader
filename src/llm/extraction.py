"""
Natural-Language Rule Extraction
=================================
Calls the Claude API with the three rule-creation tools (src/llm/tools.py)
to turn a natural-language instruction into a structured tool_use call.

This module only talks to Claude and returns its raw response — it does
not build a Rule or validate safety constraints (see src/llm/validator.py
and src/api/routes/llm_rules.py for that).
"""

from anthropic import Anthropic
from loguru import logger

from src.config.settings import ANTHROPIC_API_KEY, ALLOWED_SYMBOLS
from src.llm.tools import RULE_TOOLS

MODEL = "claude-sonnet-4-5"

SYSTEM_PROMPT = f"""You turn a user's natural-language trading instruction into a single \
structured rule by calling exactly one of the provided tools.

Rules:
- Call exactly ONE tool. Never call more than one, and never respond without \
calling a tool unless you need to ask the user a clarifying question or the \
instruction cannot be supported — in those cases, respond with text only and \
do not call any tool.
- Only these symbols are supported: {", ".join(sorted(ALLOWED_SYMBOLS))}. If the \
instruction refers to a symbol outside this list, do not call a tool — explain \
in text that the symbol is not supported.
- Be conservative about order quantities. If the instruction does not clearly \
specify a quantity (number of shares or contracts), do not guess — respond with \
text asking the user to clarify instead of calling a tool.
- Convert relative dates and durations (e.g. "in 30 days", "next month", \
"in 2 weeks") into an integer `expiry_days` for option orders.
- Convert percentage-drop/rise language into a signed `threshold` for \
price_change_pct conditions: "drops 5%" -> -5.0, "rises 5%" or "gains 5%" -> 5.0.
- If the user does not specify a cooldown, omit cooldown_seconds and let the \
tool default apply.
"""


def extract_rule(prompt: str) -> dict:
    """
    Send `prompt` to Claude with the rule-creation tools.

    Returns a dict:
        {"tool_name": str, "tool_input": dict}   if Claude called a tool
        {"text": str}                            if Claude responded with text only
    """
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=RULE_TOOLS,
        messages=[{"role": "user", "content": prompt}],
    )

    logger.info(
        f"Anthropic usage: input_tokens={response.usage.input_tokens} "
        f"output_tokens={response.usage.output_tokens}"
    )

    for block in response.content:
        if block.type == "tool_use":
            logger.info(f"LLM extracted tool call: {block.name} -> {block.input}")
            return {"tool_name": block.name, "tool_input": block.input}

    text = "".join(block.text for block in response.content if block.type == "text")
    logger.info(f"LLM did not call a tool — text response: {text!r}")
    return {"text": text}
