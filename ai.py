from __future__ import annotations
import json
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_CHAT
from prompts import SYSTEM_PROMPT, build_prompt
from embedder import retrieve_text
from tax_engine import compare_regimes, compute_deduction_gaps

client = OpenAI(api_key=OPENAI_API_KEY)


def _safe_parse(raw: str) -> dict:
    """Strip markdown fences if any, then parse JSON."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text  = "\n".join(lines).strip()
    return json.loads(text)


def generate_suggestions(profile: dict) -> dict:
    """
    Full pipeline:
    1. Compute both tax regimes + deduction gaps
    2. Retrieve embedded profile text from FAISS
    3. Build prompt and call GPT-4o-mini
    4. Parse and return structured advisory + computed numbers

    Returns a dict ready to be sent as the FastAPI response.
    """
    # Step 1: Tax engine
    tax  = compare_regimes(profile)
    gaps = compute_deduction_gaps(profile)

    # Step 2: Get profile text from FAISS
    try:
        profile_text = retrieve_text(profile["employee_code"])
    except ValueError:
        # Fallback: build text on the fly if somehow not in FAISS
        from embedder import _profile_to_text
        profile_text = _profile_to_text(profile, tax, gaps)

    # Step 3: Build prompt
    user_prompt = build_prompt(profile_text, profile, tax, gaps)

    # Step 4: Call GPT-4o-mini
    try:
        response = client.chat.completions.create(
            model=OPENAI_CHAT,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw_content = response.choices[0].message.content.strip()
    except Exception as e:
        return {"error": "OpenAI API call failed", "details": str(e)}

    # Step 5: Parse JSON
    try:
        advisory = _safe_parse(raw_content)
    except json.JSONDecodeError as e:
        return {"error": "GPT returned invalid JSON", "details": str(e), "raw": raw_content}

    # Step 6: Attach computed numbers so caller always has raw data too
    return {
        "advisory":          advisory,
        "tax_comparison":    {
            "old_regime_taxable": tax["old_regime"]["taxable_income"],
            "old_regime_tax":     tax["old_regime"]["total_tax"],
            "new_regime_taxable": tax["new_regime"]["taxable_income"],
            "new_regime_tax":     tax["new_regime"]["total_tax"],
            "recommended":        tax["recommended"],
            "savings":            tax["savings"],
            "savings_note":       tax["savings_note"],
        },
        "deduction_gaps":    gaps,
        "old_regime_detail": tax["old_regime"],
        "new_regime_detail": tax["new_regime"],
    }