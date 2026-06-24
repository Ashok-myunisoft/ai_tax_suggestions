from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
import json
import traceback

from prompts import build_prompt
from config   import DATA_PATH
from parser   import load_all_employees
from tax_engine import compare_regimes, compute_deduction_gaps
from ai       import generate_suggestions


# ── Global in-memory store ─────────────────────────────────────────────────────
_profiles: dict[str, dict] = {}
_tax_map:  dict[str, dict] = {}
_gaps_map: dict[str, dict] = {}


# ── Load system prompt from TXT ────────────────────────────────────────────────
def load_system_prompt():
    with open("prompts.txt", "r") as f:
        return f.read()


# ── Bootstrap ──────────────────────────────────────────────────────────────────
def _bootstrap() -> None:
    global _profiles, _tax_map, _gaps_map

    print("[startup] Loading employees.json ...")
    _profiles = load_all_employees(DATA_PATH)

    print(f"[startup] Loaded {len(_profiles)} employees")

    print("[startup] Computing tax regimes ...")
    _tax_map  = {code: compare_regimes(p)        for code, p in _profiles.items()}
    _gaps_map = {code: compute_deduction_gaps(p) for code, p in _profiles.items()}

    print("[startup] Ready ✅")


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    _bootstrap()
    yield


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ERP Tax Advisory — JSON Edition",
    version="2.0.0",
    lifespan=lifespan,
)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
def home():
    return {
        "status": "running",
        "employees": list(_profiles.keys()),
    }


@app.get("/employees")
def list_employees():
    return {
        "total": len(_profiles),
        "employees": [
            {
                "employee_code": code,
                "name": p["name"],
            }
            for code, p in _profiles.items()
        ],
    }


@app.get("/employee/{employee_code}")
def get_employee_profile(employee_code: str):
    if employee_code not in _profiles:
        raise HTTPException(status_code=404, detail="Employee not found")

    return {
        "profile": _profiles[employee_code],
        "tax": _tax_map[employee_code],
        "gaps": _gaps_map[employee_code],
    }


# 🔥 IMPORTANT ENDPOINT (UPDATED)
@app.post("/employee/{employee_code}/suggestions")
def get_suggestions(employee_code: str):

    if employee_code not in _profiles:
        raise HTTPException(status_code=404, detail="Employee not found")

    try:
        profile = _profiles[employee_code]
        tax     = _tax_map[employee_code]
        gaps    = _gaps_map[employee_code]

        # ✅ Load system prompt from txt
        system_prompt = load_system_prompt()

        # ✅ Convert profile to text
        profile_text = json.dumps(profile, indent=2)

        # ✅ Build user prompt
        user_prompt = build_prompt(
            profile_text=profile_text,
            profile=profile,
            tax=tax,
            gaps=gaps
        )

        # ✅ Send BOTH to AI
        result = generate_suggestions(
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "trace": traceback.format_exc()}
        )

    return {
        "employee_code": employee_code,
        "result": result
    }


@app.post("/refresh")
def refresh():
    _bootstrap()
    return {"status": "reloaded"}