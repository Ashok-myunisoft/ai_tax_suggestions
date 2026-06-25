from __future__ import annotations
import json
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_CHAT

client = OpenAI(api_key=OPENAI_API_KEY)


def _safe_parse(raw: str) -> dict:
    """Strip markdown fences if any, then parse JSON."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


def generate_suggestions(system_prompt: str, user_prompt: str) -> dict:
    """
    Calls OpenAI with given prompts.
    DOES NOT compute tax — only sends prompts and parses response.
    No employee data is retained after this call returns.
    """
    try:
        response = client.chat.completions.create(
            model=OPENAI_CHAT,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw_content = response.choices[0].message.content.strip()

    except Exception as e:
        return {"error": "OpenAI API call failed", "details": str(e)}

    try:
        advisory = _safe_parse(raw_content)
    except json.JSONDecodeError as e:
        return {
            "error": "GPT returned invalid JSON",
            "details": str(e),
            "raw": raw_content,
        }

    return advisory