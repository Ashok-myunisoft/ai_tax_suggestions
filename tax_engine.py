from __future__ import annotations

import json
import os
from functools import lru_cache

# ── Where the yearly rule files live ────────────────────────────────────────
TAX_RULES_DIR = os.path.join("data", "tax_rules")
DEFAULT_YEAR = "2026" 


# ── Load + cache a year's rules ─────────────────────────────────────────────
@lru_cache(maxsize=None)
def load_tax_rules(year: str) -> dict:
    """
    Loads data/tax_rules/{year}.json once and caches it in memory.
    Raises a clear error if the file for that year doesn't exist,
    instead of silently falling back to wrong numbers.
    """
    path = os.path.join(TAX_RULES_DIR, f"{year}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No tax rules file found for year '{year}' at {path}. "
            f"Add data/tax_rules/{year}.json before processing employees for this FY."
        )
    with open(path, "r") as f:
        return json.load(f)


def _apply_slabs(income: int, slabs: list[list]) -> int:
    """
    slabs = [[upper_limit, rate], ..., [None, rate_for_rest]]
    (JSON uses null for the open-ended top slab, which loads as None in Python)
    income must already be rounded to nearest 10.
    Returns raw tax (no cess, no surcharge).
    """
    tax = 0.0
    prev = 0
    for upper, rate in slabs:
        if upper is None:
            taxable = max(0, income - prev)
            tax += taxable * rate
            break
        if income <= upper:
            taxable = max(0, income - prev)
            tax += taxable * rate
            break
        taxable = upper - prev
        tax += taxable * rate
        prev = upper
    return int(tax)


def _apply_surcharge(income: int, tax: int, surcharge_slabs: list[list]) -> int:
    """
    surcharge_slabs = [[upper_income_limit, rate], ...] ordered ascending,
    last entry's upper_income_limit is null for "above all listed limits".
    """
    rate = 0.0
    for upper, r in surcharge_slabs:
        if upper is None or income <= upper:
            rate = r
            break
    return int(tax * rate)


def _marginal_rate_old(taxable: int, is_senior: bool, is_very_senior: bool, slabs_cfg: dict) -> float:
    """Return the marginal slab rate for old regime, read from JSON slabs."""
    if is_very_senior:
        slabs = slabs_cfg["very_senior"]
    elif is_senior:
        slabs = slabs_cfg["senior"]
    else:
        slabs = slabs_cfg["general"]

    prev = 0
    for upper, rate in slabs:
        if upper is None or taxable <= upper:
            return rate
        prev = upper
    return slabs[-1][1]


def compute_old_regime(profile: dict, rules: dict) -> dict:
    """
    Compute old-regime tax from the employee profile, using limits/slabs
    loaded from the year's tax_rules JSON instead of hardcoded numbers.
    """
    is_senior = bool(profile.get("is_senior"))
    is_very_senior = profile.get("age", 0) >= 80

    gross = profile.get("gross_salary", 0)
    hra_exempt = profile.get("hra_exemption", 0)
    lta_exempt = profile.get("lta_exemption", 0)
    ptax = profile.get("ptax", 0)
    ent_allow = profile.get("entertainment_allowance", 0)
    other_inc = profile.get("other_income_total", 0) or profile.get("total_other_income", 0)
    home_int = profile.get("home_loan_interest_24b", 0)
    rental_inc = profile.get("rental_income", 0)

    limits = rules["deduction_limits"]
    std_ded = rules["standard_deduction"]

    # Step 1: Gross salary after exemptions
    net_salary = gross - hra_exempt - lta_exempt

    # Step 2: Standard deduction
    net_salary -= std_ded

    # Step 3: Entertainment allowance (govt employees only, nominal)
    net_salary -= ent_allow

    # Step 4: PTAX
    net_salary -= ptax

    # Step 5: Other income
    total_income = net_salary + other_inc + rental_inc

    # Step 6: Home loan interest Sec 24 (capped per JSON)
    sec24_ded = min(home_int, limits["home_loan_24b"])

    # Step 7: Chapter VIA deductions
    sec_80c = min(profile.get("sec_80c_items_total", 0), limits["sec_80c"])
    nps = min(profile.get("nps_80ccd_1b", 0), limits["nps_80ccd_1b"])

    d80_self_limit = limits["health_80d_self_senior"] if is_senior else limits["health_80d_self"]
    d80_self = min(profile.get("health_ins_self_80d", 0), d80_self_limit)
    d80_par = min(profile.get("health_ins_parents_80d", 0), limits["health_80d_parents"])
    d80_total = d80_self + d80_par

    other_deds = (
        profile.get("sec_80e", 0)
        + profile.get("sec_80g", 0)
        + profile.get("sec_80tta", 0)
        + profile.get("sec_80ttb", 0)
        + profile.get("sec_80u", 0)
        + profile.get("sec_80dd", 0)
        + profile.get("sec_80ddb", 0)
        + profile.get("sec_80ee", 0)
        + profile.get("sec_80ee1", 0)
        + profile.get("sec_80eeb", 0)
    )

    total_ded = sec_80c + nps + d80_total + sec24_ded + other_deds

    # Step 8: Taxable income
    taxable = max(0, total_income - total_ded)

    # Step 9: Tax on slabs (from JSON)
    slabs_cfg = rules["old_regime_slabs"]
    if is_very_senior:
        slabs = slabs_cfg["very_senior"]
    elif is_senior:
        slabs = slabs_cfg["senior"]
    else:
        slabs = slabs_cfg["general"]

    raw_tax = _apply_slabs(taxable, slabs)

    # Step 10: 87A rebate (old regime)
    rebate_cfg = rules["rebate_87a"]
    rebate = 0
    if taxable <= rebate_cfg["old_limit"]:
        rebate = min(raw_tax, rebate_cfg["old_max_rebate"])
    tax_after_rebate = max(0, raw_tax - rebate)

    # Step 11: Surcharge (from JSON)
    surcharge = _apply_surcharge(taxable, tax_after_rebate, rules["surcharge"]["old_regime"])

    # Step 12: Cess (from JSON)
    cess = int((tax_after_rebate + surcharge) * rules["cess_rate"])
    total_tax = tax_after_rebate + surcharge + cess

    return {
        "regime": "old",
        "gross_salary": gross,
        "hra_exemption": hra_exempt,
        "standard_deduction": std_ded,
        "other_income": other_inc + rental_inc,
        "total_income": int(total_income),
        "deductions": {
            "sec_80c": sec_80c,
            "nps_80ccd_1b": nps,
            "health_80d": d80_total,
            "home_loan_24b": sec24_ded,
            "others": other_deds,
            "total": int(total_ded),
        },
        "taxable_income": int(taxable),
        "raw_tax": raw_tax,
        "rebate_87a": rebate,
        "tax_after_rebate": tax_after_rebate,
        "surcharge": surcharge,
        "cess": cess,
        "total_tax": total_tax,
        "marginal_rate": _marginal_rate_old(taxable, is_senior, is_very_senior, slabs_cfg),
    }


def compute_new_regime(profile: dict, rules: dict) -> dict:
    """
    Compute new-regime tax using slabs/limits loaded from the year's
    tax_rules JSON instead of hardcoded numbers.
    Only standard deduction + NPS employer (80CCD2) allowed.
    No 80C, no 80D, no home loan interest, no HRA.
    """
    gross = profile.get("gross_salary", 0)
    other_inc = profile.get("other_income_total", 0) or profile.get("total_other_income", 0)
    rental = profile.get("rental_income", 0)
    nps_emp = profile.get("nps_employer_80ccd2", 0)  # only allowed deduction besides std

    std_ded = rules["standard_deduction"]
    total_inc = gross - std_ded + other_inc + rental

    total_ded = nps_emp
    taxable = max(0, total_inc - total_ded)

    raw_tax = _apply_slabs(taxable, rules["new_regime_slabs"])

    # 87A rebate (new regime: zero tax if taxable <= new_limit)
    rebate_cfg = rules["rebate_87a"]
    rebate = 0
    if taxable <= rebate_cfg["new_limit"]:
        rebate = raw_tax
    tax_after_rebate = max(0, raw_tax - rebate)

    surcharge = _apply_surcharge(taxable, tax_after_rebate, rules["surcharge"]["new_regime"])
    cess = int((tax_after_rebate + surcharge) * rules["cess_rate"])
    total_tax = tax_after_rebate + surcharge + cess

    return {
        "regime": "new",
        "gross_salary": gross,
        "standard_deduction": std_ded,
        "other_income": other_inc + rental,
        "total_income": int(total_inc),
        "deductions": {
            "nps_employer": nps_emp,
            "total": int(total_ded),
        },
        "taxable_income": int(taxable),
        "raw_tax": raw_tax,
        "rebate_87a": rebate,
        "tax_after_rebate": tax_after_rebate,
        "surcharge": surcharge,
        "cess": cess,
        "total_tax": total_tax,
    }


def compare_regimes(profile: dict, year: str | None = None) -> dict:
    """
    Run both regimes and return full comparison including recommendation.

    `year` picks which data/tax_rules/{year}.json to use. If not given,
    falls back to profile["financial_year"] if present, else DEFAULT_YEAR.
    This is the key change: callers can now compute correct tax for ANY
    year just by pointing at a different JSON file — no code edits needed.
    """
    resolved_year = year or profile.get("financial_year") or DEFAULT_YEAR
    rules = load_tax_rules(resolved_year)

    old = compute_old_regime(profile, rules)
    new = compute_new_regime(profile, rules)

    if old["total_tax"] <= new["total_tax"]:
        recommended = "old"
        savings = new["total_tax"] - old["total_tax"]
        savings_note = f"Old regime saves ₹{savings:,} vs new regime."
    else:
        recommended = "new"
        savings = old["total_tax"] - new["total_tax"]
        savings_note = f"New regime saves ₹{savings:,} vs old regime."

    return {
        "financial_year": resolved_year,
        "old_regime": old,
        "new_regime": new,
        "recommended": recommended,
        "savings": savings,
        "savings_note": savings_note,
    }


def compute_deduction_gaps(profile: dict, year: str | None = None) -> dict:
    """Return unused deduction capacities for prompt context, using JSON limits."""
    resolved_year = year or profile.get("financial_year") or DEFAULT_YEAR
    rules = load_tax_rules(resolved_year)
    limits = rules["deduction_limits"]

    return {
        "sec_80c_used": min(profile.get("sec_80c_items_total", 0), limits["sec_80c"]),
        "sec_80c_gap": max(0, limits["sec_80c"] - profile.get("sec_80c_items_total", 0)),
        "nps_used": profile.get("nps_80ccd_1b", 0),
        "nps_gap": max(0, limits["nps_80ccd_1b"] - profile.get("nps_80ccd_1b", 0)),
        "health_80d_self_used": profile.get("health_ins_self_80d", 0),
        "health_80d_self_gap": max(0, limits["health_80d_self"] - profile.get("health_ins_self_80d", 0)),
        "health_80d_par_used": profile.get("health_ins_parents_80d", 0),
        "health_80d_par_gap": max(0, limits["health_80d_parents"] - profile.get("health_ins_parents_80d", 0)),
        "home_loan_int_used": profile.get("home_loan_interest_24b", 0),
        "home_loan_int_gap": max(0, limits["home_loan_24b"] - profile.get("home_loan_interest_24b", 0)),
        "sec_80tta_used": profile.get("sec_80tta", 0),
        "sec_80tta_gap": max(0, limits["sec_80tta"] - profile.get("sec_80tta", 0)),
        "hra_claimed": profile.get("hra_exemption", 0),
    }