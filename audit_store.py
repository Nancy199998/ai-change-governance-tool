"""
audit_store.py

Minimal append-only JSON audit trail. Swap this for a real database in
production, but the interface (load_all / append / update) stays the same.
"""

from __future__ import annotations

import json
import os
from typing import List, Dict

STORE_PATH = os.path.join(os.path.dirname(__file__), "audit_log.json")


def load_all() -> List[Dict]:
    if not os.path.exists(STORE_PATH):
        return []
    with open(STORE_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def append(record_dict: Dict) -> None:
    records = load_all()
    records.append(record_dict)
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


def update(record_id: str, updated_record_dict: Dict) -> bool:
    records = load_all()
    for i, r in enumerate(records):
        if r.get("record_id") == record_id:
            records[i] = updated_record_dict
            with open(STORE_PATH, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
            return True
    return False
