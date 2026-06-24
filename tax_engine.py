from __future__ import annotations
import json


# ─────────────────────────────────────────────────────────────
# Load rules based on year
# ─────────────────────────────────────────────────────────────
def load_rules(year: str):
    path = f"data/tax_rules/{year}.json"
    with open(path, "r") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────
# Common helpers
# ─────────────────────────────────────────────────────────────
def _apply_slabs(income: int, slabs):
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
    if income > 2_00_00_000:
        return int(tax * 0.25)
    if income > 1_00_00_000:
        return int(tax * 0.15)
    if income > 50_00_000:
        return int(tax * 0.10)
    return 0


# ─────────────────────────────────────────────────────────────
# OLD REGIME
# ─────────────────────────────────────────────────────────────
def compute_old_regime(profile: dict) -> dict:

    rules = load_rules(profile.get("period_code", "2026"))

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

    # Step 1
    net_salary = gross - hra_exempt - lta_exempt

    # Step 2 (from rules)
    std_ded = rules["standard_deduction"]
    net_salary -= std_ded

    # Step 3–4
    net_salary -= ent_allow
    net_salary -= ptax

    # Step 5
    total_income = net_salary + other_inc + rental_inc

    # Step 6
    sec24_ded = min(home_int, 2_00_000)

    # Step 7
    sec_80c = min(profile.get("sec_80c_items_total", 0), 1_50_000)
    nps = min(profile.get("nps_80ccd_1b", 0), 50_000)

    d80_self = min(profile.get("health_ins_self_80d", 0), 50_000 if is_senior else 25_000)
    d80_par = min(profile.get("health_ins_parents_80d", 0), 50_000)
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

    taxable = max(0, total_income - total_ded)

    # Slabs (kept dynamic later if needed)
    if is_very_senior:
        slabs = [(5_00_000, 0.00), (10_00_000, 0.20), (None, 0.30)]
    elif is_senior:
        slabs = [(3_00_000, 0.00), (5_00_000, 0.05), (10_00_000, 0.20), (None, 0.30)]
    else:
        slabs = [(2_50_000, 0.00), (5_00_000, 0.05), (10_00_000, 0.20), (None, 0.30)]

    raw_tax = _apply_slabs(taxable, slabs)

    # Rebate (can also move to rules later)
    rebate = 0
    if taxable <= rules["rebate_87a_old_limit"]:
        rebate = min(raw_tax, 12_500)

    tax_after_rebate = max(0, raw_tax - rebate)

    surcharge = _surcharge_old(taxable, tax_after_rebate)
    cess = int((tax_after_rebate + surcharge) * 0.04)

    total_tax = tax_after_rebate + surcharge + cess

    return {
        "regime": "old",
        "taxable_income": int(taxable),
        "raw_tax": raw_tax,
        "rebate_87a": rebate,
        "surcharge": surcharge,
        "cess": cess,
        "total_tax": total_tax,
    }


# ─────────────────────────────────────────────────────────────
# NEW REGIME
# ─────────────────────────────────────────────────────────────
def compute_new_regime(profile: dict) -> dict:

    rules = load_rules(profile.get("period_code", "2026"))

    gross = profile.get("gross_salary", 0)
    other_inc = profile.get("other_income_total", 0) or profile.get("total_other_income", 0)
    rental = profile.get("rental_income", 0)
    nps_emp = profile.get("nps_employer_80ccd2", 0)

    std_ded = rules["standard_deduction"]

    total_inc = gross - std_ded + other_inc + rental
    taxable = max(0, total_inc - nps_emp)

    slabs = rules["new_regime_slabs"]
    raw_tax = _apply_slabs(taxable, slabs)

    rebate = 0
    if taxable <= rules["rebate_87a_new_limit"]:
        rebate = raw_tax

    tax_after_rebate = max(0, raw_tax - rebate)

    surcharge = _surcharge_new(taxable, tax_after_rebate)
    cess = int((tax_after_rebate + surcharge) * 0.04)

    total_tax = tax_after_rebate + surcharge + cess

    return {
        "regime": "new",
        "taxable_income": int(taxable),
        "raw_tax": raw_tax,
        "rebate_87a": rebate,
        "surcharge": surcharge,
        "cess": cess,
        "total_tax": total_tax,
    }


# ─────────────────────────────────────────────────────────────
# COMPARISON
# ─────────────────────────────────────────────────────────────
def compare_regimes(profile: dict) -> dict:
    old = compute_old_regime(profile)
    new = compute_new_regime(profile)

    if old["total_tax"] <= new["total_tax"]:
        recommended = "old"
        savings = new["total_tax"] - old["total_tax"]
    else:
        recommended = "new"
        savings = old["total_tax"] - new["total_tax"]

    return {
        "old_regime": old,
        "new_regime": new,
        "recommended": recommended,
        "savings": savings,
    }


# ─────────────────────────────────────────────────────────────
# GAPS (UNCHANGED)
# ─────────────────────────────────────────────────────────────
def compute_deduction_gaps(profile: dict) -> dict:
    return {
        "sec_80c_used": min(profile.get("sec_80c_items_total", 0), 1_50_000),
        "sec_80c_gap": max(0, 1_50_000 - profile.get("sec_80c_items_total", 0)),
        "nps_used": profile.get("nps_80ccd_1b", 0),
        "nps_gap": max(0, 50_000 - profile.get("nps_80ccd_1b", 0)),
        "health_80d_self_used": profile.get("health_ins_self_80d", 0),
        "health_80d_self_gap": max(0, 25_000 - profile.get("health_ins_self_80d", 0)),
        "health_80d_par_used": profile.get("health_ins_parents_80d", 0),
        "health_80d_par_gap": max(0, 50_000 - profile.get("health_ins_parents_80d", 0)),
        "home_loan_int_used": profile.get("home_loan_interest_24b", 0),
        "home_loan_int_gap": max(0, 2_00_000 - profile.get("home_loan_interest_24b", 0)),
        "sec_80tta_used": profile.get("sec_80tta", 0),
        "sec_80tta_gap": max(0, 10_000 - profile.get("sec_80tta", 0)),
    }