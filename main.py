from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
import json
import traceback

from cleaner import clean_and_extract_rows
from prompts import build_prompt
from parser import extract_profile
from tax_engine import compare_regimes, compute_deduction_gaps
from ai import generate_suggestions


def load_system_prompt() -> str:
    with open("prompts.txt", "r") as f:
        return f.read()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="ERP Tax Advisory",
    version="4.0.0",
    lifespan=lifespan,
)


@app.get("/")
def home():
    return {
        "status": "running",
        "version": "4.0.0",
        "note": "running successfully",
    }


@app.post("/suggestions", openapi_extra={
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "description": "Paste the full ERP wrapper JSON exactly as received.",
                    "properties": {
                        "Id":             {"type": "integer", "example": 0},
                        "Body":           {"type": "string",  "description": "JSON-stringified employee rows array"},
                        "OUId":           {"type": "integer", "example": 0},
                        "ValidationBody": {"nullable": True},
                        "Status":         {"nullable": True},
                    },
                    "required": ["Body"],
                }
            }
        },
    }
})
async def get_suggestions(request: Request):
    raw_body = await request.body()

    try:
        rows = clean_and_extract_rows(raw_body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not rows:
        raise HTTPException(status_code=400, detail="Extracted rows array is empty.")

    try:
        profile = extract_profile(rows)
        tax  = compare_regimes(profile)
        gaps = compute_deduction_gaps(profile)

        sys_prompt  = load_system_prompt()
        user_prompt = build_prompt(
            profile_text=json.dumps(profile, indent=2),
            profile=profile,
            tax=tax,
            gaps=gaps,
        )
        result = generate_suggestions(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "trace": traceback.format_exc()},
        )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result)

    return {
        "employee_code": profile.get("employee_code"),
        "name":          profile.get("name"),
        "result":        result,
    }