# job_scout/db/repositories/auto_apply_rules.py
"""Repository for the auto_apply_rules table."""

from typing import Dict, List, Optional


def get_rules(db, active_only: bool = True) -> List[Dict]:
    """Return all auto-apply rules, ordered by priority descending."""
    params = {"order": "priority.desc", "limit": 100}
    if active_only:
        params["is_active"] = "eq.true"
    try:
        return db._request("GET", "auto_apply_rules", params=params) or []
    except Exception as e:
        print(f"auto_apply_rules.get_rules: {e}")
        return []


def create_rule(db, rule: Dict) -> Optional[Dict]:
    """Insert a new auto-apply rule. Returns the created record."""
    required = {"name", "conditions", "action"}
    missing = required - rule.keys()
    if missing:
        raise ValueError(f"auto_apply_rules.create_rule: missing fields {missing}")
    payload = {
        "name":       rule["name"],
        "is_active":  rule.get("is_active", True),
        "priority":   rule.get("priority", 0),
        "conditions": rule["conditions"],
        "action":     rule["action"],
    }
    try:
        result = db._request("POST", "auto_apply_rules", json=payload)
        return result[0] if result else None
    except Exception as e:
        print(f"auto_apply_rules.create_rule: {e}")
        return None


def update_rule(db, rule_id: str, updates: Dict) -> Optional[Dict]:
    """Patch an existing rule by ID."""
    try:
        result = db._request(
            "PATCH",
            "auto_apply_rules",
            params={"id": f"eq.{rule_id}"},
            json=updates,
        )
        return result[0] if result else None
    except Exception as e:
        print(f"auto_apply_rules.update_rule: {e}")
        return None


def delete_rule(db, rule_id: str) -> bool:
    """Delete a rule by ID. Returns True on success."""
    try:
        db._request("DELETE", "auto_apply_rules", params={"id": f"eq.{rule_id}"})
        return True
    except Exception as e:
        print(f"auto_apply_rules.delete_rule: {e}")
        return False


def toggle_rule(db, rule_id: str, active: bool) -> Optional[Dict]:
    """Enable or disable a rule without deleting it."""
    return update_rule(db, rule_id, {"is_active": active})
