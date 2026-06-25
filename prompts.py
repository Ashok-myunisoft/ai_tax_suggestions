from __future__ import annotations


def build_prompt(profile_text: str, profile: dict, tax: dict, gaps: dict) -> str:
    old = tax["old_regime"]
    new = tax["new_regime"]
    recommended = tax["recommended"].upper()

    if tax["recommended"] == "new":
        regime_context = (
            "REGIME DECISION: NEW REGIME IS RECOMMENDED.\n"
            f"Tax under New Regime = Rs {new['total_tax']:,} vs Old Regime Rs {old['total_tax']:,}.\n"
            f"New Regime taxable income = Rs {new['taxable_income']:,}.\n"
            + (
                "Tax is ZERO because taxable income is below the Rs 12,00,000 rebate limit under Sec 87A.\n"
                if new["total_tax"] == 0
                else f"Tax liability = Rs {new['total_tax']:,}.\n"
            )
            + "\n"
            "IMPORTANT: Under New Regime, deductions under 80C, 80D, NPS 80CCD(1B),\n"
            "Sec 24b home loan interest, HRA, LTA do NOT reduce tax.\n"
            "Do NOT recommend these as tax-saving instruments.\n"
            "You may mention them for financial planning only, and must explicitly state\n"
            "they will NOT save tax under the chosen regime."
        )
    else:
        marginal_pct = int(old.get("marginal_rate", 0) * 100)
        regime_context = (
            "REGIME DECISION: OLD REGIME IS RECOMMENDED.\n"
            f"Tax under Old Regime = Rs {old['total_tax']:,} vs New Regime Rs {new['total_tax']:,}.\n"
            f"Old Regime taxable income = Rs {old['taxable_income']:,}.\n"
            f"Marginal tax rate = {marginal_pct}%.\n"
            "\n"
            "All deduction gaps below are valid tax-saving opportunities.\n"
            "Generate one suggestion per non-zero gap.\n"
            "Calculate estimated tax saving using the marginal rate above."
        )

    senior_label = "Senior Citizen" if profile.get("is_senior") else "Non-Senior Citizen"
    recommended_tax = new["total_tax"] if tax["recommended"] == "new" else old["total_tax"]

    lines = [
        "EMPLOYEE TAX PROFILE FY 2025-26",
        "",
        f"NAME        : {profile['name']}",
        f"DESIGNATION : {profile['designation']}",
        f"AGE         : {profile['age']} | {senior_label}",
        "",
        "SALARY BREAKDOWN:",
        f"  Gross Salary        : Rs {profile.get('gross_salary', 0):,}",
        f"  Standard Deduction  : Rs 75,000",
        f"  Other Income        : Rs {profile.get('other_income_total', 0) or profile.get('total_other_income', 0):,}",
        f"  HRA Exemption       : Rs {profile.get('hra_exemption', 0):,}",
        f"  LTA Exemption       : Rs {profile.get('lta_exemption', 0):,}",
        "",
        regime_context,
        "",
        "BOTH REGIME CALCULATIONS (pre-computed, do not recalculate):",
        "  OLD REGIME:",
        f"    Taxable Income     : Rs {old['taxable_income']:,}",
        f"    Deductions Total   : Rs {old['deductions']['total']:,}",
        f"      80C              : Rs {old['deductions']['sec_80c']:,}",
        f"      NPS 80CCD(1B)    : Rs {old['deductions']['nps_80ccd_1b']:,}",
        f"      Health 80D       : Rs {old['deductions']['health_80d']:,}",
        f"      Home Loan Sec 24b: Rs {old['deductions']['home_loan_24b']:,}",
        f"    Base Tax           : Rs {old['raw_tax']:,}",
        f"    Rebate 87A         : Rs {old['rebate_87a']:,}",
        f"    Surcharge          : Rs {old['surcharge']:,}",
        f"    Cess (4%)          : Rs {old['cess']:,}",
        f"    TOTAL TAX OLD      : Rs {old['total_tax']:,}",
        "",
        "  NEW REGIME:",
        f"    Taxable Income     : Rs {new['taxable_income']:,}",
        f"    Base Tax           : Rs {new['raw_tax']:,}",
        f"    Rebate 87A         : Rs {new['rebate_87a']:,}",
        f"    Surcharge          : Rs {new['surcharge']:,}",
        f"    Cess (4%)          : Rs {new['cess']:,}",
        f"    TOTAL TAX NEW      : Rs {new['total_tax']:,}",
        "",
        f"  RECOMMENDED         : {recommended} REGIME",
        f"  SAVINGS             : Rs {tax['savings']:,}",
        "",
        "DEDUCTION GAPS (only relevant if OLD regime recommended):",
        f"  Sec 80C    : Used Rs {gaps['sec_80c_used']:,} of Rs 1,50,000  | Gap Rs {gaps['sec_80c_gap']:,}",
        f"  NPS 80CCD1B: Used Rs {gaps['nps_used']:,} of Rs 50,000     | Gap Rs {gaps['nps_gap']:,}",
        f"  80D Self   : Used Rs {gaps['health_80d_self_used']:,} of Rs 25,000     | Gap Rs {gaps['health_80d_self_gap']:,}",
        f"  80D Parents: Used Rs {gaps['health_80d_par_used']:,} of Rs 50,000     | Gap Rs {gaps['health_80d_par_gap']:,}",
        f"  Sec 24b    : Used Rs {gaps['home_loan_int_used']:,} of Rs 2,00,000  | Gap Rs {gaps['home_loan_int_gap']:,}",
        f"  80TTA      : Used Rs {gaps['sec_80tta_used']:,} of Rs 10,000     | Gap Rs {gaps['sec_80tta_gap']:,}",
        "",
        "TDS STATUS:",
        f"  Remaining Months in FY : {profile.get('remaining_months', 'N/A')}",
        f"  TDS Per Month          : Rs {profile.get('tds_per_month', 0):,}",
        f"  Total TDS Paid So Far  : Rs {profile.get('tds_from_salary', 0):,}",
        f"  Total Tax Liability    : Rs {recommended_tax:,}",
        "",
        "Generate suggestions strictly following the regime decision above.",
        "If NEW regime: confirm zero/low tax, state no deduction action needed for tax purposes.",
        "If OLD regime: give one suggestion per non-zero gap with exact instrument and rupee amount.",
    ]

    return "\n".join(lines)