from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import traceback

from config   import DATA_PATH
from parser   import load_all_employees
from tax_engine import compare_regimes, compute_deduction_gaps
from embedder import embed_all, is_ready
from ai       import generate_suggestions

# ── Global in-memory store ─────────────────────────────────────────────────────
_profiles: dict[str, dict] = {}   # employee_code → profile
_tax_map:  dict[str, dict] = {}   # employee_code → compare_regimes result
_gaps_map: dict[str, dict] = {}   # employee_code → deduction gaps


def _bootstrap() -> None:
    """Load JSON, compute taxes, embed all — called at startup and /refresh."""
    global _profiles, _tax_map, _gaps_map

    print("[startup] Loading employees.json ...")
    _profiles = load_all_employees(DATA_PATH)
    print(f"[startup] Loaded {len(_profiles)} employees: {list(_profiles.keys())}")

    print("[startup] Computing tax regimes ...")
    _tax_map  = {code: compare_regimes(p)         for code, p in _profiles.items()}
    _gaps_map = {code: compute_deduction_gaps(p)  for code, p in _profiles.items()}

    print("[startup] Embedding into FAISS ...")
    embed_all(_profiles, _tax_map, _gaps_map)
    print("[startup] All done. Server ready.")


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    _bootstrap()
    yield


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ERP Tax Advisory — JSON Edition",
    version="2.0.0",
    description="Indian income tax suggestions using GPT-4o-mini. Old vs New regime comparison included.",
    lifespan=lifespan,
)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def home():
    return {
        "status":    "running",
        "version":   "2.0.0",
        "employees": list(_profiles.keys()),
        "faiss_ready": is_ready(),
        "endpoints": {
            "profile":     "GET  /employee/{employee_code}",
            "suggestions": "POST /employee/{employee_code}/suggestions",
            "list":        "GET  /employees",
            "refresh":     "POST /refresh",
        },
    }


@app.get("/employees", tags=["Employees"])
def list_employees():
    """List all loaded employee codes with their names."""
    return {
        "total": len(_profiles),
        "employees": [
            {
                "employee_code": code,
                "name":          p["name"],
                "designation":   p["designation"],
                "age":           p["age"],
            }
            for code, p in _profiles.items()
        ],
    }


@app.get("/employee/{employee_code}", tags=["Step 1 — Profile"])
def get_employee_profile(employee_code: str):
    """
    Returns the full parsed profile + both tax regime breakdowns for an employee.
    No AI call — instant response.
    """
    if employee_code not in _profiles:
        raise HTTPException(
            status_code=404,
            detail=f"Employee '{employee_code}' not found. Available: {list(_profiles.keys())}",
        )

    profile = _profiles[employee_code]
    tax     = _tax_map[employee_code]
    gaps    = _gaps_map[employee_code]

    return {
        "employee_code":   employee_code,
        "name":            profile["name"],
        "designation":     profile["designation"],
        "age":             profile["age"],
        "is_senior":       profile["is_senior"],
        "gross_salary":    profile.get("gross_salary", 0),
        "other_income":    profile.get("other_income_total", 0) or profile.get("total_other_income", 0),
        "hra_exemption":   profile.get("hra_exemption", 0),
        "lta_exemption":   profile.get("lta_exemption", 0),
        "remaining_months":profile.get("remaining_months", 0),
        "tds_per_month":   profile.get("tds_per_month", 0),
        "tax_comparison": {
            "old_regime_taxable": tax["old_regime"]["taxable_income"],
            "old_regime_tax":     tax["old_regime"]["total_tax"],
            "new_regime_taxable": tax["new_regime"]["taxable_income"],
            "new_regime_tax":     tax["new_regime"]["total_tax"],
            "recommended":        tax["recommended"],
            "savings":            tax["savings"],
            "savings_note":       tax["savings_note"],
        },
        "old_regime_detail": tax["old_regime"],
        "new_regime_detail": tax["new_regime"],
        "deduction_gaps":    gaps,
        "raw_deductions": {
            "sec_80c_items_total": profile.get("sec_80c_items_total", 0),
            "nps_80ccd_1b":        profile.get("nps_80ccd_1b", 0),
            "health_ins_self":     profile.get("health_ins_self_80d", 0),
            "health_ins_parents":  profile.get("health_ins_parents_80d", 0),
            "home_loan_interest":  profile.get("home_loan_interest_24b", 0),
            "sec_80tta":           profile.get("sec_80tta", 0),
            "sec_80e":             profile.get("sec_80e", 0),
            "sec_80g":             profile.get("sec_80g", 0),
        },
    }


@app.post("/employee/{employee_code}/suggestions", tags=["Step 2 — AI Suggestions"])
def get_suggestions(employee_code: str):
    """
    Calls GPT-4o-mini and returns full tax-saving suggestions for the employee.
    Includes old vs new regime comparison, deduction gap analysis, priority actions.
    """
    if employee_code not in _profiles:
        raise HTTPException(
            status_code=404,
            detail=f"Employee '{employee_code}' not found. Available: {list(_profiles.keys())}",
        )

    if not is_ready():
        raise HTTPException(status_code=503, detail="FAISS index not ready. Try /refresh.")

    try:
        result = generate_suggestions(_profiles[employee_code])
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "trace": traceback.format_exc()})

    if "error" in result:
        raise HTTPException(status_code=500, detail=result)

    return {
        "employee_code":  employee_code,
        "name":           _profiles[employee_code]["name"],
        "designation":    _profiles[employee_code]["designation"],
        **result,
    }


@app.post("/refresh", tags=["Admin"])
def refresh():
    """Reload employees.json and re-embed all profiles into FAISS."""
    try:
        _bootstrap()
        return {
            "status":    "success",
            "employees": list(_profiles.keys()),
            "message":   f"Reloaded {len(_profiles)} employees and rebuilt FAISS index.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))