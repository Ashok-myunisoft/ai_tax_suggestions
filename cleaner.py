from __future__ import annotations
import json
import re


def clean_and_extract_rows(raw_bytes: bytes) -> list[dict]:
    raw_text = raw_bytes.decode("utf-8", errors="replace")

    raw_text = raw_text.replace("\u201c", '"').replace("\u201d", '"')
    raw_text = raw_text.replace("\u2018", "'").replace("\u2019", "'")

    raw_text = re.sub(r'[\u2000-\u200A\u202F\u205F\u3000\u00A0\u200B\uFEFF]', '', raw_text)

    raw_text = raw_text.strip()

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Outer JSON parse failed after cleaning: {e}\nFirst 300 chars: {raw_text[:300]}")

    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object or array, got {type(payload)}")

    if "Body" in payload:
        body = payload["Body"]

        if isinstance(body, list):
            return body

        if isinstance(body, str):
            inner = body.replace("\u201c", '"').replace("\u201d", '"')
            inner = re.sub(r'[\u2000-\u200A\u202F\u205F\u3000\u00A0\u200B\uFEFF]', '', inner)
            inner = inner.strip()
            try:
                rows = json.loads(inner)
            except json.JSONDecodeError as e:
                raise ValueError(f"Inner Body JSON parse failed: {e}\nFirst 300 chars: {inner[:300]}")
            if not isinstance(rows, list):
                raise ValueError("Body parsed but is not a list")
            return rows

    if "rows" in payload and isinstance(payload["rows"], list):
        return payload["rows"]

    raise ValueError(
        "Could not find employee rows. "
        "Expected ERP wrapper with 'Body' field, a direct array, or {'rows': [...]}."
    )