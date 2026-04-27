# job_scout/pipeline/rules_engine.py
"""
Evaluates auto_apply_rules conditions against a job dict.
Rule JSON schema matches what 40_pipeline.py writes to DB.
"""

from typing import Dict, List, Optional


def _eval_condition(job: Dict, cond: Dict) -> bool:
    """Evaluate a single {field, op, value} condition against a job."""
    field = cond.get("field", "")
    op = cond.get("op", "==")
    value = cond.get("value")

    job_val = job.get(field)

    if op == ">=":
        return (job_val or 0) >= value
    if op == "<=":
        return (job_val or 0) <= value
    if op == ">":
        return (job_val or 0) > value
    if op == "<":
        return (job_val or 0) < value
    if op == "==":
        return job_val == value
    if op == "!=":
        return job_val != value
    if op == "in":
        return job_val in (value or [])
    if op == "not_in":
        return job_val not in (value or [])
    if op == "any_in":
        # job_val can be a list (e.g. categories) or a string
        if isinstance(job_val, list):
            return any(v in job_val for v in (value or []))
        return str(job_val or "") in (value or [])
    return False


def _eval_tree(job: Dict, node: Dict) -> bool:
    """Recursively evaluate a condition tree with all_of / any_of / none_of."""
    if "all_of" in node:
        return all(_eval_tree(job, c) for c in node["all_of"])
    if "any_of" in node:
        return any(_eval_tree(job, c) for c in node["any_of"])
    if "none_of" in node:
        return not any(_eval_tree(job, c) for c in node["none_of"])
    # Leaf condition
    if "field" in node:
        return _eval_condition(job, node)
    return True


def match_rule(job: Dict, rule: Dict) -> bool:
    """Return True if a job satisfies all conditions in a rule."""
    if not rule.get("is_active", True):
        return False
    conditions = rule.get("conditions") or {}
    return _eval_tree(job, conditions)


def find_matching_rule(job: Dict, rules: List[Dict]) -> Optional[Dict]:
    """
    Evaluate rules in priority order (highest first).
    Returns the first matching rule, or None.
    """
    sorted_rules = sorted(rules, key=lambda r: r.get("priority", 0), reverse=True)
    for rule in sorted_rules:
        if match_rule(job, rule):
            return rule
    return None


def load_rules(db) -> List[Dict]:
    """Load active auto_apply_rules from DB."""
    try:
        return db._request("GET", "auto_apply_rules", params={
            "is_active": "eq.true",
            "order": "priority.desc",
            "limit": 100,
        }) or []
    except Exception as e:
        print(f"rules load error: {e}")
        return []
