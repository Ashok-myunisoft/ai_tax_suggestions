from __future__ import annotations
import numpy as np
import faiss
from openai import OpenAI
from config import OPENAI_API_KEY, FAISS_DIM, OPENAI_EMBED

client = OpenAI(api_key=OPENAI_API_KEY)

# Global state
_index:    faiss.IndexFlatL2 | None = None
_code_map: list[str]                = []   # position → employee_code
_text_map: dict[str, str]           = {}   # employee_code → profile text


def _profile_to_text(profile: dict, tax: dict, gaps: dict) -> str:
    """
    Convert a structured profile + tax comparison + gaps into a
    rich plain-text block suitable for embedding and for prompting.
    """
    old = tax["old_regime"]
    new = tax["new_regime"]

    lines = [
        f"Employee: {profile['name']} | {profile['designation']} | Age: {profile['age']}",
        f"Employee Code: {profile['employee_code']} | PAN: {profile['pan']}",
        f"Gross Salary (FY 2025-26): Rs {profile.get('gross_salary', 0):,}",
        f"Standard Deduction: Rs 75,000",
        f"Other Income: Rs {profile.get('other_income_total', 0) or profile.get('total_other_income', 0):,}",
        f"HRA Exemption Claimed: Rs {profile.get('hra_exemption', 0):,}",
        f"LTA Exemption Claimed: Rs {profile.get('lta_exemption', 0):,}",
        "",
        "── 80C Investments ──",
        f"  PF Contribution (auto): Rs {profile.get('sec_80c_items_total', 0):,}",
        f"  80C Used: Rs {gaps['sec_80c_used']:,} | Gap: Rs {gaps['sec_80c_gap']:,} (limit Rs 1,50,000)",
        "",
        "── NPS (80CCD 1B) ──",
        f"  Used: Rs {gaps['nps_used']:,} | Gap: Rs {gaps['nps_gap']:,} (limit Rs 50,000)",
        "",
        "── Health Insurance (80D) ──",
        f"  Self: Rs {gaps['health_80d_self_used']:,} | Gap: Rs {gaps['health_80d_self_gap']:,} (limit Rs 25,000)",
        f"  Parents: Rs {gaps['health_80d_par_used']:,} | Gap: Rs {gaps['health_80d_par_gap']:,} (limit Rs 50,000)",
        "",
        "── Home Loan Interest (Sec 24b) ──",
        f"  Used: Rs {gaps['home_loan_int_used']:,} | Gap: Rs {gaps['home_loan_int_gap']:,} (limit Rs 2,00,000)",
        "",
        "── 80TTA Savings Interest ──",
        f"  Used: Rs {gaps['sec_80tta_used']:,} | Gap: Rs {gaps['sec_80tta_gap']:,} (limit Rs 10,000)",
        "",
        "── Tax Computation ──",
        f"  OLD REGIME | Taxable Income: Rs {old['taxable_income']:,} | Tax: Rs {old['total_tax']:,}",
        f"    (80C: Rs {old['deductions']['sec_80c']:,} | NPS: Rs {old['deductions']['nps_80ccd_1b']:,} | 80D: Rs {old['deductions']['health_80d']:,} | Sec24: Rs {old['deductions']['home_loan_24b']:,})",
        f"  NEW REGIME | Taxable Income: Rs {new['taxable_income']:,} | Tax: Rs {new['total_tax']:,}",
        f"    (Only standard deduction + employer NPS; no 80C/80D/HRA allowed)",
        f"",
        f"  RECOMMENDED: {tax['recommended'].upper()} REGIME — {tax['savings_note']}",
    ]
    return "\n".join(lines)


def _embed(texts: list[str]) -> np.ndarray:
    resp = client.embeddings.create(model=OPENAI_EMBED, input=texts)
    vecs = [item.embedding for item in resp.data]
    arr  = np.array(vecs, dtype="float32")
    faiss.normalize_L2(arr)
    return arr


def embed_all(profiles: dict[str, dict], tax_map: dict[str, dict], gaps_map: dict[str, dict]) -> None:
    """
    Called at startup. Builds a fresh FAISS index for all employees.
    profiles  = {employee_code: profile_dict}
    tax_map   = {employee_code: compare_regimes_result}
    gaps_map  = {employee_code: compute_deduction_gaps_result}
    """
    global _index, _code_map, _text_map

    codes = list(profiles.keys())
    texts = [_profile_to_text(profiles[c], tax_map[c], gaps_map[c]) for c in codes]

    print(f"[embedder] Embedding {len(codes)} employees ...")
    vecs = _embed(texts)

    _index    = faiss.IndexFlatIP(FAISS_DIM)   # inner-product on L2-normalised = cosine
    _index.add(vecs)
    _code_map = codes
    _text_map = {c: t for c, t in zip(codes, texts)}
    print(f"[embedder] FAISS index ready with {_index.ntotal} vectors.")


def retrieve_text(employee_code: str) -> str:
    """
    Retrieve the stored profile text for a given employee_code via FAISS lookup.
    Falls back to direct dict lookup if FAISS is not ready.
    """
    if employee_code in _text_map:
        return _text_map[employee_code]
    raise ValueError(f"Employee {employee_code} not found in FAISS store.")


def is_ready() -> bool:
    return _index is not None and len(_code_map) > 0