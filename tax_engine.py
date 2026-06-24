from __future__ import annotations


def _apply_slabs(income: int, slabs: list[tuple[int, float]]) -> int:
    """
    slabs = [(upper_limit, rate), ..., (None, rate_for_rest)]
    income must already be rounded to nearest 10.
    Returns raw tax (no cess, no surcharge).
    """
    tax       = 0.0
    prev      = 0
    for upper, rate in slabs:
        if upper is None:
            taxable = max(0, income - prev)
            tax    += taxable * rate
            break
        if income <= upper:
            taxable = max(0, income - prev)
            tax    += taxable * rate
            break
        taxable = upper - prev
        tax    += taxable * rate
        prev    = upper
    return int(tax)


def _surcharge_old(income: int, tax: int) -> int:
    if income > 5_00_00_000:
        return int(tax * 0.37)
    if income > 2_00_00_000:
        return int(tax * 0.25)
    if income > 1_00_00_000:
        return int(tax * 0.15)
    if income > 50_00_000:
        return int(tax * 0.10)
    return 0


def _surcharge_new(income: int, tax: int) -> int:
    # New regime: max surcharge capped at 25%
    if income > 2_00_00_000:
        return int(tax * 0.25)
    if income > 1_00_00_000:
        return int(tax * 0.15)
    if income > 50_00_000:
        return int(tax * 0.10)
    return 0


def _marginal_rate_old(taxable: int, is_senior: bool, is_very_senior: bool) -> float:
    """Return the marginal slab rate for old regime."""
    if is_very_senior:
        if taxable <= 5_00_000:   return 0.0
        if taxable <= 10_00_000:  return 0.20
        return 0.30
    if is_senior:
        if taxable <= 3_00_000:   return 0.0
        if taxable <= 5_00_000:   return 0.05
        if taxable <= 10_00_000:  return 0.20
        return 0.30
    if taxable <= 2_50_000:   return 0.0
    if taxable <= 5_00_000:   return 0.05
    if taxable <= 10_00_000:  return 0.20
    return 0.30


def compute_old_regime(profile: dict) -> dict:
    """
    Compute old-regime tax from the employee profile.
    Deductions considered:
      - Standard deduction ₹75,000
      - 80C (max ₹1,50,000)
      - 80CCD(1B) NPS (max ₹50,000)
      - 80D self + parents
      - Sec 24 home loan interest (max ₹2,00,000)
      - HRA exemption (as per ERP)
      - Other deductions: 80E, 80G, 80TTA/TTB, 80U etc.
    """
    is_senior      = bool(profile.get("is_senior"))
    is_very_senior = profile.get("age", 0) >= 80

    gross          = profile.get("gross_salary", 0)
    hra_exempt     = profile.get("hra_exemption", 0)
    lta_exempt     = profile.get("lta_exemption", 0)
    ptax           = profile.get("ptax", 0)
    ent_allow      = profile.get("entertainment_allowance", 0)
    other_inc      = profile.get("other_income_total", 0) or profile.get("total_other_income", 0)
    home_int       = profile.get("home_loan_interest_24b", 0)
    rental_inc     = profile.get("rental_income", 0)

    # Step 1: Gross salary after exemptions
    net_salary = gross - hra_exempt - lta_exempt

    # Step 2: Standard deduction
    std_ded = 75_000
    net_salary -= std_ded

    # Step 3: Entertainment allowance (for govt employees only, nominal)
    net_salary -= ent_allow

    # Step 4: PTAX
    net_salary -= ptax

    # Step 5: Other income
    total_income = net_salary + other_inc + rental_inc

    # Step 6: Home loan interest Sec 24 (max 2L for self-occupied)
    sec24_ded = min(home_int, 2_00_000)

    # Step 7: Chapter VIA deductions
    sec_80c   = min(profile.get("sec_80c_items_total", 0), 1_50_000)
    nps       = min(profile.get("nps_80ccd_1b", 0), 50_000)

    # 80D: self limit 25k (50k if senior), parents limit 25k (50k if parents senior – use 50k conservatively if non-zero)
    d80_self   = min(profile.get("health_ins_self_80d", 0), 50_000 if is_senior else 25_000)
    d80_par    = min(profile.get("health_ins_parents_80d", 0), 50_000)
    d80_total  = d80_self + d80_par

    other_deds = (
        profile.get("sec_80e", 0) +
        profile.get("sec_80g", 0) +
        profile.get("sec_80tta", 0) +
        profile.get("sec_80ttb", 0) +
        profile.get("sec_80u", 0) +
        profile.get("sec_80dd", 0) +
        profile.get("sec_80ddb", 0) +
        profile.get("sec_80ee", 0) +
        profile.get("sec_80ee1", 0) +
        profile.get("sec_80eeb", 0)
    )

    total_ded = sec_80c + nps + d80_total + sec24_ded + other_deds

    # Step 8: Taxable income
    taxable = max(0, total_income - total_ded)

    # Step 9: Tax on slabs
    if is_very_senior:
        slabs = [
            (5_00_000,  0.00),
            (10_00_000, 0.20),
            (None,      0.30),
        ]
    elif is_senior:
        slabs = [
            (3_00_000,  0.00),
            (5_00_000,  0.05),
            (10_00_000, 0.20),
            (None,      0.30),
        ]
    else:
        slabs = [
            (2_50_000,  0.00),
            (5_00_000,  0.05),
            (10_00_000, 0.20),
            (None,      0.30),
        ]

    raw_tax = _apply_slabs(taxable, slabs)

    # Step 10: 87A rebate (old regime: taxable <= 5L → full rebate, max ₹12,500)
    rebate = 0
    if taxable <= 5_00_000:
        rebate = min(raw_tax, 12_500)
    tax_after_rebate = max(0, raw_tax - rebate)

    # Step 11: Surcharge
    surcharge = _surcharge_old(taxable, tax_after_rebate)

    # Step 12: Cess 4%
    cess = int((tax_after_rebate + surcharge) * 0.04)

    total_tax = tax_after_rebate + surcharge + cess

    return {
        "regime":             "old",
        "gross_salary":       gross,
        "hra_exemption":      hra_exempt,
        "standard_deduction": std_ded,
        "other_income":       other_inc + rental_inc,
        "total_income":       int(total_income),
        "deductions": {
            "sec_80c":       sec_80c,
            "nps_80ccd_1b":  nps,
            "health_80d":    d80_total,
            "home_loan_24b": sec24_ded,
            "others":        other_deds,
            "total":         int(total_ded),
        },
        "taxable_income":    int(taxable),
        "raw_tax":           raw_tax,
        "rebate_87a":        rebate,
        "tax_after_rebate":  tax_after_rebate,
        "surcharge":         surcharge,
        "cess":              cess,
        "total_tax":         total_tax,
        "marginal_rate":     _marginal_rate_old(taxable, is_senior, is_very_senior),
    }


def compute_new_regime(profile: dict) -> dict:
    """
    Compute new-regime tax (FY 2025-26).
    Only standard deduction ₹75,000 + NPS employer (80CCD2) allowed.
    No 80C, no 80D, no home loan interest, no HRA.
    87A rebate: zero tax if net taxable income <= ₹12,00,000.
    """
    gross     = profile.get("gross_salary", 0)
    other_inc = profile.get("other_income_total", 0) or profile.get("total_other_income", 0)
    rental    = profile.get("rental_income", 0)
    nps_emp   = profile.get("nps_employer_80ccd2", 0)   # only allowed deduction besides std

    std_ded  = 75_000
    total_inc = gross - std_ded + other_inc + rental

    # Employer NPS contribution deduction (80CCD2: 10% of basic – ERP provides the amount)
    total_ded = nps_emp
    taxable   = max(0, total_inc - total_ded)

    # New regime slabs FY 2025-26
    slabs = [
        (4_00_000,  0.00),
        (8_00_000,  0.05),
        (12_00_000, 0.10),
        (16_00_000, 0.15),
        (20_00_000, 0.20),
        (24_00_000, 0.25),
        (None,      0.30),
    ]
    raw_tax = _apply_slabs(taxable, slabs)

    # 87A rebate (new): zero tax if taxable <= 12L
    rebate = 0
    if taxable <= 12_00_000:
        rebate = raw_tax
    tax_after_rebate = max(0, raw_tax - rebate)

    # Surcharge (new regime, max 25%)
    surcharge = _surcharge_new(taxable, tax_after_rebate)

    # Cess 4%
    cess = int((tax_after_rebate + surcharge) * 0.04)

    total_tax = tax_after_rebate + surcharge + cess

    return {
        "regime":             "new",
        "gross_salary":       gross,
        "standard_deduction": std_ded,
        "other_income":       other_inc + rental,
        "total_income":       int(total_inc),
        "deductions": {
            "nps_employer":  nps_emp,
            "total":         int(total_ded),
        },
        "taxable_income":    int(taxable),
        "raw_tax":           raw_tax,
        "rebate_87a":        rebate,
        "tax_after_rebate":  tax_after_rebate,
        "surcharge":         surcharge,
        "cess":              cess,
        "total_tax":         total_tax,
    }


def compare_regimes(profile: dict) -> dict:
    """
    Run both regimes and return full comparison including recommendation.
    """
    old = compute_old_regime(profile)
    new = compute_new_regime(profile)

    if old["total_tax"] <= new["total_tax"]:
        recommended   = "old"
        savings       = new["total_tax"] - old["total_tax"]
        savings_note  = f"Old regime saves ₹{savings:,} vs new regime."
    else:
        recommended  = "new"
        savings      = old["total_tax"] - new["total_tax"]
        savings_note = f"New regime saves ₹{savings:,} vs old regime."

    return {
        "old_regime":    old,
        "new_regime":    new,
        "recommended":   recommended,
        "savings":       savings,
        "savings_note":  savings_note,
    }


def compute_deduction_gaps(profile: dict) -> dict:
    """Return unused deduction capacities for prompt context."""
    return {
        "sec_80c_used":        min(profile.get("sec_80c_items_total", 0), 1_50_000),
        "sec_80c_gap":         max(0, 1_50_000 - profile.get("sec_80c_items_total", 0)),
        "nps_used":            profile.get("nps_80ccd_1b", 0),
        "nps_gap":             max(0, 50_000 - profile.get("nps_80ccd_1b", 0)),
        "health_80d_self_used":profile.get("health_ins_self_80d", 0),
        "health_80d_self_gap": max(0, 25_000 - profile.get("health_ins_self_80d", 0)),
        "health_80d_par_used": profile.get("health_ins_parents_80d", 0),
        "health_80d_par_gap":  max(0, 50_000 - profile.get("health_ins_parents_80d", 0)),
        "home_loan_int_used":  profile.get("home_loan_interest_24b", 0),
        "home_loan_int_gap":   max(0, 2_00_000 - profile.get("home_loan_interest_24b", 0)),
        "sec_80tta_used":      profile.get("sec_80tta", 0),
        "sec_80tta_gap":       max(0, 10_000 - profile.get("sec_80tta", 0)),
        "hra_claimed":         profile.get("hra_exemption", 0),
    }