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