from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any


# ── SlNo → field name mapping ─────────────────────────────────────────────────
# Only the SlNos we actually care about for tax computation.

_SLNO_FIELD: dict[int, str] = {
    1:  "net_taxable_salary",
    2:  "gross_salary",
    6:  "gross_salary_total",
    16: "balance_after_exemption",
    17: "total_salary_deductions",
    18: "standard_deduction",
    19: "entertainment_allowance",
    20: "ptax",
    21: "rental_income",
    22: "other_income_total",
    25: "other_income_misc",
    27: "home_loan_interest_24b",
    28: "total_other_income",
    29: "gross_total_income",
    30: "total_deductions_chapter",
    31: "sec_80c_group_total",
    51: "nps_80ccd_1b",
    52: "nps_employer_80ccd2",
    53: "other_deductions_via",
    54: "health_ins_self_80d",
    55: "health_ins_parents_80d",
    56: "sec_80dd",
    57: "sec_80ddb",
    58: "sec_80e",
    59: "sec_80g",
    61: "sec_80tta",
    62: "sec_80ttb",
    63: "sec_80u",
    64: "sec_80ee",
    67: "sec_80ee1",
    68: "sec_80eeb",
    70: "taxable_income",
    71: "income_tax_calculated",
    72: "tax_rebate_87a",
    80: "total_tax_payable",
    81: "surcharge",
    82: "cess",
    83: "total_tax_liability",
    84: "tds_from_salary",
    85: "tax_paid_outside",
    86: "total_tax_paid",
    87: "balance_tax_refundable",
    94: "remaining_months",
    98: "tds_per_month",
}

# SlNos that carry their value in ValueAmount (not Amount)
_USE_VALUE_AMOUNT: set[int] = {1, 28, 29, 70, 71, 80, 81, 82, 83, 87}

# 80C sub-item SlNos (32-50) — sum Amount across all of these
_80C_SLNOS: set[int] = set(range(32, 51))

# HRA and LTA SlNos
_HRA_SLNO = 8
_LTA_SLNO = 11


def _int(v: Any) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def _age(dob_str: str) -> int:
    """
    Handles both ISO date strings ('1968-09-16') and the ERP's
    ASP.NET JSON date format ('/Date(-40714200000)/').
    """
    try:
        m = re.match(r"/Date\((-?\d+)\)/", dob_str or "")
        if m:
            ms  = int(m.group(1))
            dob = date(1970, 1, 1) + timedelta(milliseconds=ms)
        else:
            dob = date.fromisoformat(dob_str)
        today = date.today()
        return (
            today.year - dob.year
            - ((today.month, today.day) < (dob.month, dob.day))
        )
    except Exception:
        return 0


def extract_profile(rows: list[dict]) -> dict:
    """
    Convert a flat list of SlNo ledger rows for ONE employee
    into a clean structured profile dict.

    Called directly with the rows parsed from the POST request body.
    No file I/O here.
    """
    if not rows:
        raise ValueError("Empty row list — cannot extract profile.")

    # Identity fields — same across all rows, read from first row
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

    # Numeric fields — defaults to zero
    numeric: dict[str, int] = {f: 0 for f in _SLNO_FIELD.values()}
    numeric["sec_80c_items_total"] = 0
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
    numeric["sec_80c_used"] = min(numeric["sec_80c_items_total"], 150_000)
    numeric["sec_80c_gap"]  = max(0, 150_000 - numeric["sec_80c_items_total"])

    numeric["nps_used"] = numeric["nps_80ccd_1b"]
    numeric["nps_gap"]  = max(0, 50_000 - numeric["nps_80ccd_1b"])

    numeric["health_80d_self"] = numeric["health_ins_self_80d"]
    numeric["health_80d_par"]  = numeric["health_ins_parents_80d"]
    numeric["health_80d_used"] = (
        numeric["health_ins_self_80d"] + numeric["health_ins_parents_80d"]
    )
    numeric["health_80d_gap"] = max(0, 25_000 - numeric["health_ins_self_80d"])

    profile["is_senior"] = profile["age"] >= 60
    profile.update(numeric)
    return profile