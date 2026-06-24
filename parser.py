from __future__ import annotations
import json
from datetime import date
from typing import Any
import re
from datetime import date, timedelta


# ── SlNo → field name mapping ─────────────────────────────────────────────────
# Only the SlNos we actually care about for tax computation.
# 80C sub-items (32-50) are summed separately.

_SLNO_FIELD: dict[int, str] = {
    1:  "net_taxable_salary",       # ValueAmount  – income chargeable under salaries
    2:  "gross_salary",             # Amount       – sec 17(1)
    6:  "gross_salary_total",       # Amount
    16: "balance_after_exemption",  # Amount       – after HRA/LTA
    17: "total_salary_deductions",  # Amount       – standard ded + PTAX
    18: "standard_deduction",       # Amount       – ₹75 000 (FY25-26)
    19: "entertainment_allowance",  # Amount
    20: "ptax",                     # Amount
    21: "rental_income",            # Amount
    22: "other_income_total",       # Amount       – any other sources
    25: "other_income_misc",        # Amount
    27: "home_loan_interest_24b",   # Amount       – Sec 24 interest
    28: "total_other_income",       # ValueAmount
    29: "gross_total_income",       # ValueAmount
    30: "total_deductions_chapter", # ValueAmount
    31: "sec_80c_group_total",      # Amount       – ERP-computed 80C total
    51: "nps_80ccd_1b",             # Amount       – self NPS (max 50 000)
    52: "nps_employer_80ccd2",      # Amount       – employer NPS
    53: "other_deductions_via",     # Amount       – other Chapter VIA
    54: "health_ins_self_80d",      # Amount       – max 25 000
    55: "health_ins_parents_80d",   # Amount       – max 50 000 (senior 50k)
    56: "sec_80dd",                 # Amount
    57: "sec_80ddb",                # Amount
    58: "sec_80e",                  # Amount
    59: "sec_80g",                  # Amount
    61: "sec_80tta",                # Amount       – max 10 000
    62: "sec_80ttb",                # Amount       – max 50 000 senior
    63: "sec_80u",                  # Amount
    64: "sec_80ee",                 # Amount
    67: "sec_80ee1",                # Amount
    68: "sec_80eeb",                # Amount
    70: "taxable_income",           # ValueAmount  – final taxable income (ERP)
    71: "income_tax_calculated",    # ValueAmount  – ERP-computed income tax
    72: "tax_rebate_87a",           # Amount       – rebate amount
    80: "total_tax_payable",        # ValueAmount
    81: "surcharge",                # ValueAmount
    82: "cess",                     # ValueAmount
    83: "total_tax_liability",      # ValueAmount
    84: "tds_from_salary",          # Amount
    85: "tax_paid_outside",         # Amount
    86: "total_tax_paid",           # Amount
    87: "balance_tax_refundable",   # ValueAmount
    94: "remaining_months",         # Amount
    98: "tds_per_month",            # Amount
}

# SlNos that carry their value in ValueAmount (not Amount)
_USE_VALUE_AMOUNT: set[int] = {1, 28, 29, 70, 71, 80, 81, 82, 83, 87}

# 80C sub-item SlNos (32-50) – we sum Amount across all of these
_80C_SLNOS: set[int] = set(range(32, 51))

# HRA-related SlNos
_HRA_SLNO  = 8
_LTA_SLNO  = 11


def _int(v: Any) -> int:
    """Safe int conversion."""
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def _age(dob_str: str) -> int:
    """Handles both ISO ('1968-09-16') and the ERP's ASP.NET date
    format ('/Date(-40714200000)/')."""
    try:
        m = re.match(r"/Date\((-?\d+)\)/", dob_str or "")
        if m:
            ms = int(m.group(1))
            dob = date(1970, 1, 1) + timedelta(milliseconds=ms)
        else:
            dob = date.fromisoformat(dob_str)
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except Exception:
        return 0


def _load_raw(path: str) -> list[list[dict]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # The JSON is either: [[...emp1...], [...emp2...], ...] directly
    # or wrapped in one more list. Handle both.
    if isinstance(data, list) and len(data) > 0:
        if isinstance(data[0], list):
            return data           # already [[rows], [rows], ...]
        if isinstance(data[0], dict):
            return [data]         # single employee, not wrapped
    raise ValueError("Unexpected JSON structure")


def extract_profile(rows: list[dict]) -> dict:
    """
    Convert a flat list of SlNo ledger rows for ONE employee
    into a clean structured profile dict.
    """
    if not rows:
        raise ValueError("Empty row list")

    # Identity fields – same across all rows
    first = rows[0]
    profile: dict[str, Any] = {
        "employee_id":   first.get("EmployeeId"),
        "employee_code": first.get("EmployeeCode", ""),
        "name":          first.get("EmployeeName", ""),
        "pan":           first.get("PANNo", ""),
        "designation":   first.get("Designation", ""),
        "dob":           first.get("DOB", ""),
        "doj":           first.get("DOJ", ""),
        "age":           _age(first.get("DOB", "")),
        "period_code":   first.get("PeriodCode", "2026"),
    }

    # Numeric fields – defaults
    numeric: dict[str, int] = {f: 0 for f in _SLNO_FIELD.values()}
    numeric["sec_80c_items_total"] = 0   # sum of 32-50
    numeric["hra_exemption"]       = 0
    numeric["lta_exemption"]       = 0

    for row in rows:
        slno = _int(row.get("SlNo"))
        amt  = _int(row.get("Amount"))
        vamt = _int(row.get("ValueAmount"))

        if slno in _SLNO_FIELD:
            field = _SLNO_FIELD[slno]
            numeric[field] = vamt if slno in _USE_VALUE_AMOUNT else amt

        elif slno in _80C_SLNOS:
            numeric["sec_80c_items_total"] += amt

        elif slno == _HRA_SLNO:
            numeric["hra_exemption"] = amt

        elif slno == _LTA_SLNO:
            numeric["lta_exemption"] = amt

    # ── Derived convenience fields ────────────────────────────────────────────

    # 80C total = PF (in items) + other 80C items; cap already in ERP as sec_80c_group_total
    # We use sec_80c_items_total as raw used amount (some employees have PF in SlNo 33 inside 32-50)
    numeric["sec_80c_used"]    = min(numeric["sec_80c_items_total"], 150_000)
    numeric["sec_80c_gap"]     = max(0, 150_000 - numeric["sec_80c_items_total"])

    numeric["nps_used"]        = numeric["nps_80ccd_1b"]
    numeric["nps_gap"]         = max(0, 50_000 - numeric["nps_80ccd_1b"])

    numeric["health_80d_self"] = numeric["health_ins_self_80d"]
    numeric["health_80d_par"]  = numeric["health_ins_parents_80d"]
    numeric["health_80d_used"] = numeric["health_ins_self_80d"] + numeric["health_ins_parents_80d"]
    numeric["health_80d_gap"]  = max(0, 25_000 - numeric["health_ins_self_80d"])

    # Is senior citizen? (age >= 60)
    profile["is_senior"] = profile["age"] >= 60

    profile.update(numeric)
    return profile


def load_all_employees(path: str) -> dict[str, dict]:
    """
    Returns {employee_code: profile_dict} for every employee in the JSON.
    """
    raw_groups = _load_raw(path)
    result: dict[str, dict] = {}
    for rows in raw_groups:
        if not rows:
            continue
        try:
            p = extract_profile(rows)
            result[p["employee_code"]] = p
        except Exception as e:
            print(f"[parser] Skipping a group due to error: {e}")
    return result