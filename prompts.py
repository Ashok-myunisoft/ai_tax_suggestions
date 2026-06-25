from __future__ import annotations


def build_prompt(profile_text: str, profile: dict, tax: dict, gaps: dict) -> str:
    old = tax["old_regime"]
    new = tax["new_regime"]
    recommended = tax["recommended"]  # "old" or "new"

    old_tax   = old["total_tax"]
    new_tax   = new["total_tax"]
    tax_gap   = abs(old_tax - new_tax)
    marginal  = old.get("marginal_rate", 0)
    marginal_pct = int(marginal * 100)

    # ── Flip analysis (Python-computed, not LLM-guessed) ─────────────────────
    # How much MORE deduction is needed to make old_regime_tax == new_regime_tax?
    # deduction_needed = tax_gap / marginal_rate
    if recommended == "new" and marginal > 0:
        deduction_needed_to_flip = int(tax_gap / marginal)
        total_remaining_gap = (
            gaps["sec_80c_gap"]
            + gaps["nps_gap"]
            + gaps["health_80d_self_gap"]
            + gaps["health_80d_par_gap"]
            + gaps["home_loan_int_gap"]
            + gaps["sec_80tta_gap"]
        )
        can_flip = total_remaining_gap >= deduction_needed_to_flip
        flip_note = (
            f"To make Old Regime tax equal New Regime tax, additional deductions of "
            f"Rs {deduction_needed_to_flip:,} are needed (tax gap Rs {tax_gap:,} / marginal rate {marginal_pct}%). "
            f"Total available unused deduction capacity across all sections = Rs {total_remaining_gap:,}. "
            + (
                "It IS mathematically possible to flip the recommendation if the employee fully utilizes available deductions — validate with tax engine."
                if can_flip else
                f"Even fully utilizing all available deduction limits (Rs {total_remaining_gap:,}) cannot close this gap. New Regime remains superior."
            )
        )
    else:
        deduction_needed_to_flip = 0
        total_remaining_gap = (
            gaps["sec_80c_gap"]
            + gaps["nps_gap"]
            + gaps["health_80d_self_gap"]
            + gaps["health_80d_par_gap"]
            + gaps["home_loan_int_gap"]
            + gaps["sec_80tta_gap"]
        )
        flip_note = "Old Regime is already recommended. Maximize declared deductions to reduce tax further."

    # ── Per-section tax saving (Python-computed at actual marginal rate) ──────
    def tax_saving(gap: int) -> int:
        return int(gap * marginal)

    sec_80c_saving      = tax_saving(gaps["sec_80c_gap"])
    nps_saving          = tax_saving(gaps["nps_gap"])
    health_self_saving  = tax_saving(gaps["health_80d_self_gap"])
    health_par_saving   = tax_saving(gaps["health_80d_par_gap"])
    home_loan_saving    = tax_saving(gaps["home_loan_int_gap"])
    tta_saving          = tax_saving(gaps["sec_80tta_gap"])

    # ── Correct headline ──────────────────────────────────────────────────────
    if recommended == "new":
        headline = f"New Regime Recommended — Estimated Tax Saving of Rs {tax_gap:,} vs Old Regime"
    else:
        headline = f"Old Regime Recommended — Estimated Tax Saving of Rs {tax_gap:,} vs New Regime"

    # ── can_old_regime_become_better ─────────────────────────────────────────
    can_old_become_better = (recommended == "new") and can_flip if recommended == "new" else False

    senior_label = "Senior Citizen" if profile.get("is_senior") else "Non-Senior Citizen"

    lines = [
        "=== EMPLOYEE TAX PROFILE — FY 2025-26 ===",
        "",
        f"NAME              : {profile['name']}",
        f"DESIGNATION       : {profile['designation']}",
        f"AGE               : {profile['age']} ({senior_label})",
        f"PAN               : {profile['pan']}",
        "",
        "=== INCOME ===",
        f"Gross Salary           : Rs {profile.get('gross_salary', 0):,}",
        f"HRA Exemption          : Rs {profile.get('hra_exemption', 0):,}",
        f"LTA Exemption          : Rs {profile.get('lta_exemption', 0):,}",
        f"Standard Deduction     : Rs 75,000",
        f"Other Income           : Rs {profile.get('other_income_total', 0) or profile.get('total_other_income', 0):,}",
        f"Rental Income          : Rs {profile.get('rental_income', 0):,}",
        "",
        "=== DECLARED DEDUCTIONS (use exactly these in output) ===",
        f"80C — PF               : Rs {profile.get('sec_80c_items_total', 0):,}  (of which employee PF = Rs {profile.get('sec_80c_items_total', 0):,})",
        f"80CCD(1B) NPS          : Rs {profile.get('nps_80ccd_1b', 0):,}",
        f"80CCD(2) Employer NPS  : Rs {profile.get('nps_employer_80ccd2', 0):,}",
        f"80D Self               : Rs {profile.get('health_ins_self_80d', 0):,}",
        f"80D Parents            : Rs {profile.get('health_ins_parents_80d', 0):,}",
        f"Home Loan Interest 24b : Rs {profile.get('home_loan_interest_24b', 0):,}",
        f"80TTA                  : Rs {profile.get('sec_80tta', 0):,}",
        f"80E                    : Rs {profile.get('sec_80e', 0):,}",
        f"80G                    : Rs {profile.get('sec_80g', 0):,}",
        f"TOTAL DECLARED         : Rs {gaps['sec_80c_used'] + profile.get('nps_80ccd_1b', 0) + profile.get('health_ins_self_80d', 0) + profile.get('health_ins_parents_80d', 0) + profile.get('home_loan_interest_24b', 0) + profile.get('sec_80tta', 0):,}",
        "",
        "=== PRE-COMPUTED TAX — DO NOT RECALCULATE, USE EXACTLY ===",
        "OLD REGIME:",
        f"  Gross Total Income   : Rs {old['total_income']:,}",
        f"  Total Deductions     : Rs {old['deductions']['total']:,}",
        f"    80C                : Rs {old['deductions']['sec_80c']:,}",
        f"    NPS 80CCD(1B)      : Rs {old['deductions']['nps_80ccd_1b']:,}",
        f"    Health 80D         : Rs {old['deductions']['health_80d']:,}",
        f"    Home Loan 24b      : Rs {old['deductions']['home_loan_24b']:,}",
        f"    Others             : Rs {old['deductions']['others']:,}",
        f"  Taxable Income       : Rs {old['taxable_income']:,}",
        f"  Base Tax             : Rs {old['raw_tax']:,}",
        f"  Rebate 87A           : Rs {old['rebate_87a']:,}",
        f"  Surcharge            : Rs {old['surcharge']:,}",
        f"  Cess (4%)            : Rs {old['cess']:,}",
        f"  TOTAL TAX OLD        : Rs {old_tax:,}",
        f"  Marginal Rate        : {marginal_pct}%",
        "",
        "NEW REGIME:",
        f"  Gross Total Income   : Rs {new['total_income']:,}",
        f"  Taxable Income       : Rs {new['taxable_income']:,}",
        f"  Base Tax             : Rs {new['raw_tax']:,}",
        f"  Rebate 87A           : Rs {new['rebate_87a']:,}",
        f"  Surcharge            : Rs {new['surcharge']:,}",
        f"  Cess (4%)            : Rs {new['cess']:,}",
        f"  TOTAL TAX NEW        : Rs {new_tax:,}",
        "",
        f"RECOMMENDED REGIME     : {recommended.upper()}",
        f"TAX SAVING             : Rs {tax_gap:,}",
        f"CORRECT HEADLINE       : {headline}",
        "",
        "=== FLIP ANALYSIS — PRE-COMPUTED, USE EXACTLY ===",
        flip_note,
        f"can_old_regime_become_better : {str(can_old_become_better).lower()}",
        "",
        "=== DEDUCTION GAPS & TAX SAVINGS AT ACTUAL MARGINAL RATE ({marginal_pct}%) ===",
        f"(All tax savings below are computed as: gap × {marginal_pct}% — use these exact figures)",
        "",
        f"80C      : Used Rs {gaps['sec_80c_used']:,} / Rs 1,50,000 | Gap Rs {gaps['sec_80c_gap']:,} | Tax saving if utilized: Rs {sec_80c_saving:,}",
        f"NPS      : Used Rs {gaps['nps_used']:,} / Rs 50,000    | Gap Rs {gaps['nps_gap']:,} | Tax saving if utilized: Rs {nps_saving:,}",
        f"80D Self : Used Rs {gaps['health_80d_self_used']:,} / Rs 25,000    | Gap Rs {gaps['health_80d_self_gap']:,} | Tax saving if utilized: Rs {health_self_saving:,}",
        f"80D Par  : Used Rs {gaps['health_80d_par_used']:,} / Rs 50,000    | Gap Rs {gaps['health_80d_par_gap']:,} | Tax saving if utilized: Rs {health_par_saving:,}",
        f"Sec 24b  : Used Rs {gaps['home_loan_int_used']:,} / Rs 2,00,000  | Gap Rs {gaps['home_loan_int_gap']:,} | Tax saving if utilized: Rs {home_loan_saving:,}",
        f"80TTA    : Used Rs {gaps['sec_80tta_used']:,} / Rs 10,000     | Gap Rs {gaps['sec_80tta_gap']:,} | Tax saving if utilized: Rs {tta_saving:,}",
        f"TOTAL UNUSED CAPACITY  : Rs {total_remaining_gap:,}",
        "",
        "=== TDS STATUS ===",
        f"Remaining Months       : {profile.get('remaining_months', 'N/A')}",
        f"TDS Per Month          : Rs {profile.get('tds_per_month', 0):,}",
        f"Total TDS Paid So Far  : Rs {profile.get('tds_from_salary', 0):,}",
        f"Total Tax Liability    : Rs {new_tax if recommended == 'new' else old_tax:,}",
        "",
        "=== SECTION-WISE INSTRUMENT MAPPING (use exactly for eligible_instruments) ===",
        "80C eligible: EPF, PPF, ELSS, Life Insurance Premium, NSC, Tax Saver FD (5yr), Principal Repayment of Housing Loan, Tuition Fees, Sukanya Samriddhi",
        "80CCD(1B) eligible: NPS Tier 1 only",
        "80D Self eligible: Health insurance premium for self, spouse, children",
        "80D Parents eligible: Health insurance premium for parents (Rs 50,000 if parents are senior citizens)",
        "Sec 24b eligible: Home loan interest on self-occupied or let-out property",
        "80TTA eligible: Interest from savings bank account",
        "",
        "=== INSTRUCTIONS ===",
        "1. Use ONLY the pre-computed figures above. Do not recalculate any tax number.",
        "2. Use ONLY the pre-computed tax savings per section above. Do not apply 30% generically.",
        "3. The flip_analysis must use the pre-computed deduction_needed_to_flip and total_remaining_gap.",
        "4. The headline must be exactly as specified in CORRECT HEADLINE above.",
        "5. eligible_instruments for each section must use only the instruments listed in SECTION-WISE INSTRUMENT MAPPING.",
        "6. would_flip_recommendation for each deduction must be false unless can_old_regime_become_better is true AND that section's gap alone closes the tax_gap.",
        "7. For New Regime: frame all deduction opportunities as financial planning, not tax saving.",
        "8. Apply all RULES from the system prompt.",
    ]

    return "\n".join(lines)