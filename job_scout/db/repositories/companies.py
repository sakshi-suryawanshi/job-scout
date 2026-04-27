# job_scout/db/repositories/companies.py
"""Company repository — thin wrappers over PostgREST for company entities."""

from typing import List, Dict, Optional
from job_scout.db.client import get_db


def get_companies(active_only: bool = True, limit: int = 1000) -> List[Dict]:
    return get_db().get_companies(active_only=active_only, limit=limit)


def get_company_by_id(company_id: str) -> Optional[Dict]:
    return get_db().get_company_by_id(company_id)


def get_company_by_name(name: str) -> Optional[Dict]:
    return get_db().get_company_by_name(name)


def find_or_create_company(name: str, defaults: Dict = None) -> Optional[str]:
    return get_db().find_or_create_company(name, defaults)


def add_company(company: Dict) -> Optional[Dict]:
    return get_db().add_company(company)


def add_companies_bulk(companies: List[Dict]) -> int:
    return get_db().add_companies_bulk(companies)


def update_company(company_id: str, updates: Dict) -> bool:
    return get_db().update_company(company_id, updates)


def delete_company(company_id: str) -> bool:
    return get_db().delete_company(company_id)
