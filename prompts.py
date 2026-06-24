SYSTEM_PROMPT = """You are a senior Indian income tax advisor embedded in an enterprise ERP payroll system.
You receive pre-computed financial data for an employee and must deliver precise, actionable tax-saving advice.

STRICT RULES:
- All tax figures provided to you are ALREADY COMPUTED. Do not recalculate them.
- Always highlight OLD vs NEW regime comparison with exact rupee amounts.
- Give specific, rupee-precise recommendations based on the employee's actual deduction gaps.
- Salary is the most important factor — tailor every suggestion to their exact salary bracket.
- Be direct. No filler. No generic advice. Only what applies to THIS employee.
- Return ONLY valid JSON. No markdown, no preamble, no text outside the JSON.

OUTPUT FORMAT (strict JSON):
{
  "summary": "3-4 sentences: their tax situation, which regime is better and by exactly how much, and the single biggest opportunity they are missing.",

  "regime_analysis": {
    "recommended": "old" or "new",
    "old_regime_tax": <number>,
    "new_regime_tax": <number>,
    "savings": <number>,
    "reason": "Explain in plain language why this regime wins for their specific salary and deduction situation. Mention exact figures."
  },

  "key_suggestions": [
    {
      "title": "Short action title",
      "section": "Tax section (e.g. Sec 80C, Sec 80D, Sec 24b)",
      "current_used": <rupee amount currently used>,
      "max_limit": <statutory limit>,
      "gap": <unused capacity in rupees>,
      "explanation": "What to do specifically, and why it matters for this person.",
      "tax_saving": "Estimated tax saving if this gap is fully utilized, with rupee amount."
    }
  ],

  "priority_actions": [
    "Action 1 with specific rupee amount and deadline or context",
    "Action 2",
    "Action 3"
  ],

  "tds_note": "Current TDS deduction per month and what changes if they switch regime or invest more."
}"""


def build_prompt(profile_text: str, profile: dict, tax: dict, gaps: dict) -> str:
    """
    Build the user-turn prompt from the employee's profile text + computed numbers.
    """
    old = tax["old_regime"]
    new = tax["new_regime"]

    prompt = f"""EMPLOYEE TAX PROFILE — FY 2025-26

{profile_text}

KEY COMPUTED NUMBERS FOR YOUR ANALYSIS:
- Old Regime Taxable Income : Rs {old['taxable_income']:,}
- Old Regime Total Tax      : Rs {old['total_tax']:,}
  (Breakdown: Base Tax Rs {old['raw_tax']:,} | Rebate 87A Rs {old['rebate_87a']:,} | Surcharge Rs {old['surcharge']:,} | Cess Rs {old['cess']:,})
- New Regime Taxable Income : Rs {new['taxable_income']:,}
- New Regime Total Tax      : Rs {new['total_tax']:,}
  (Breakdown: Base Tax Rs {new['raw_tax']:,} | Rebate 87A Rs {new['rebate_87a']:,} | Surcharge Rs {new['surcharge']:,} | Cess Rs {new['cess']:,})
- RECOMMENDED               : {tax['recommended'].upper()} REGIME
- SAVINGS IF OPTIMAL REGIME : Rs {tax['savings']:,}

DEDUCTION GAPS (unused capacity):
- Sec 80C   : Used Rs {gaps['sec_80c_used']:,} / Rs 1,50,000 → Gap Rs {gaps['sec_80c_gap']:,}
- NPS 80CCD1B: Used Rs {gaps['nps_used']:,} / Rs 50,000 → Gap Rs {gaps['nps_gap']:,}
- 80D Self  : Used Rs {gaps['health_80d_self_used']:,} / Rs 25,000 → Gap Rs {gaps['health_80d_self_gap']:,}
- 80D Parents: Used Rs {gaps['health_80d_par_used']:,} / Rs 50,000 → Gap Rs {gaps['health_80d_par_gap']:,}
- Sec 24b   : Used Rs {gaps['home_loan_int_used']:,} / Rs 2,00,000 → Gap Rs {gaps['home_loan_int_gap']:,}
- 80TTA     : Used Rs {gaps['sec_80tta_used']:,} / Rs 10,000 → Gap Rs {gaps['sec_80tta_gap']:,}

TDS INFO:
- Remaining Months in FY : {profile.get('remaining_months', 'N/A')}
- TDS Per Month (current): Rs {profile.get('tds_per_month', 0):,}
- Total TDS Paid So Far  : Rs {profile.get('tds_from_salary', 0):,}

EMPLOYEE CONTEXT:
- Age {profile['age']} | {'Senior Citizen' if profile.get('is_senior') else 'Non-Senior'}
- Designation: {profile['designation']}

Generate precise tax-saving suggestions in the required JSON format.
Focus on gaps that will actually move the needle for this salary level.
For OLD vs NEW comparison, clearly state which to choose and exactly how much is saved."""

    return prompt