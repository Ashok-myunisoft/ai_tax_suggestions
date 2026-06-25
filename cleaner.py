from __future__ import annotations
import json
import re


def clean_and_extract_rows(raw_bytes: bytes) -> list[dict]:
    # Decode bytes to string
    raw_text = raw_bytes.decode("utf-8", errors="replace")

    # Replace curly/smart quotes with straight double quotes
    raw_text = raw_text.replace("\u201c", '"').replace("\u201d", '"')
    raw_text = raw_text.replace("\u2018", "'").replace("\u2019", "'")

    # Strip invisible unicode spaces
    raw_text = re.sub(r'[\u2000-\u200A\u202F\u205F\u3000\u00A0\u200B\uFEFF]', '', raw_text)

    raw_text = raw_text.strip()

    # Parse outer JSON
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Outer JSON parse failed after cleaning: {e}\nFirst 300 chars: {raw_text[:300]}")

    # Shape 1: raw array posted directly
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object or array, got {type(payload)}")

    # Shape 2: ERP wrapper — Body is a JSON string
    if "Body" in payload:
        body = payload["Body"]

        if isinstance(body, list):
            # Swagger already parsed the string into a list
            return body

        if isinstance(body, str):
            # Clean the inner Body string too
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

    # Shape 3: direct rows object
    if "rows" in payload and isinstance(payload["rows"], list):
        return payload["rows"]

    raise ValueError(
        "Could not find employee rows. "
        "Expected ERP wrapper with 'Body' field, a direct array, or {'rows': [...]}."
    )