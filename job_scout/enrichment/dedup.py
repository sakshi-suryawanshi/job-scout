# job_scout/enrichment/dedup.py
# Moved from worker/scraping/dedup.py — single canonical dedup implementation.
"""
Job deduplication and global-remote filtering utilities.
"""

import hashlib
import re
from typing import Dict


_COMPANY_SUFFIXES = re.compile(
    r"\b(inc\.?|ltd\.?|llc|co\.?|corp\.?|gmbh|pvt\.?|pte\.?|pty\.?|limited|incorporated)\b",
    re.IGNORECASE,
)

_YC_BATCH = re.compile(r"\((?:YC\s*)?[WSF]\d{2}\)", re.IGNORECASE)

# Strip seniority qualifiers so "Senior Backend Engineer" deduplicates with
# "Backend Engineer" and "Lead Backend Engineer" at the same company.
_SENIORITY = re.compile(
    r"\b(senior|sr\.?|lead|principal|staff|jr\.?|junior|associate|"
    r"mid-?level|entry-?level|ii|iii|iv|i\b)\b",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation/suffixes/seniority, collapse whitespace."""
    text = (text or "").lower().strip()
    text = _COMPANY_SUFFIXES.sub("", text)
    text = _YC_BATCH.sub("", text)
    text = _SENIORITY.sub("", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_company_name(name: str) -> str:
    """Normalize a company name for dedup comparison.

    Strips legal suffixes and YC batch tags only — does NOT strip seniority
    words (those are job-title concepts, not company name concepts).

    Examples:
      "Stripe Inc"          → "stripe"
      "Acme Corp."          → "acme"
      "Linear (YC S20)"     → "linear"
      "OpenAI"              → "openai"
      "Meta Platforms Inc." → "meta platforms"
    """
    text = (name or "").lower().strip()
    text = _COMPANY_SUFFIXES.sub("", text)
    text = _YC_BATCH.sub("", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def generate_job_fingerprint(title: str, company_name: str) -> str:
    """SHA256 fingerprint from normalized title + company name."""
    norm_title = normalize_text(title)
    norm_company = normalize_text(company_name)
    raw = f"{norm_company}::{norm_title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _normalize_apply_url(url: str) -> str:
    """Strip trailing slash, query string, and fragment so URL variants of the
    same job collapse to one value. Used by rebuild_fingerprints to decide
    which dupes share a real underlying posting vs. which are legitimate
    re-listings."""
    if not url:
        return ""
    s = (url or "").strip().lower()
    # cut query string and fragment
    s = s.split("?", 1)[0].split("#", 1)[0]
    s = s.rstrip("/")
    return s


def rebuild_fingerprints(db, dry_run: bool = True, progress_callback=None) -> dict:
    """Recompute every job's fingerprint using the *current* normalize_text
    rules, then collapse duplicates.

    Why this exists:
      `normalize_text` has been tightened over time (e.g. seniority words are
      now stripped). Jobs inserted before a rule change have stale fingerprints
      that no longer match what a fresh insert would produce — so dedup at
      insert time misses them and we accumulate duplicates.

    Strategy:
      1. Fetch every job with id, title, fingerprint, apply_url, source_board,
         source_boards, discovered_at, company_id and the joined company name.
      2. For each row, compute the canonical fingerprint from (title, company_name).
      3. Group rows by canonical fingerprint.
      4. For groups > 1 row:
         - Sub-group by normalized apply_url. Rows with the same normalized URL
           are TRUE duplicates of one another (same role, same listing, same
           board URL with trailing-slash/query variation).
         - Within each apply_url sub-group, KEEP the oldest row (preserves the
           original discovered_at + accumulated source_boards). DELETE the rest.
         - Rows with different normalized apply_urls within the same fingerprint
           group are kept (legitimate re-listings or regional variants — we don't
           drop them).
         - The kept row gets its fingerprint UPDATED to the canonical value.
      5. Rows whose stored fingerprint already equals the canonical one and have
         no duplicates are left untouched.

    Always non-destructive in dry_run=True mode — returns the same stats but
    skips PATCH/DELETE.
    """
    import collections

    # Page through the jobs table — Supabase/PostgREST caps the row count per
    # response (default 1000), so we must offset until exhausted.
    rows: list = []
    offset = 0
    page = 1000
    while True:
        batch = db._request("GET", "jobs", params={
            "select": "id,title,fingerprint,apply_url,source_board,source_boards,discovered_at,company_id,companies(name)",
            "offset": offset,
            "limit": page,
            "order": "discovered_at.desc",
        }) or []
        if not batch:
            break
        rows.extend(batch)
        if progress_callback:
            progress_callback(f"Fetched {len(rows)} jobs…", min(0.3, len(rows) / 5000))
        if len(batch) < page:
            break
        offset += page
        if offset > 50000:
            break  # safety cap

    stats = {
        "scanned":            len(rows),
        "groups_with_dupes":  0,
        "rows_deleted":       0,
        "fingerprints_fixed": 0,
        "dry_run":            dry_run,
    }
    if not rows:
        return stats

    # Compute canonical fingerprint per row (skip rows without title or company name).
    canon: dict = {}
    for r in rows:
        co_name = ((r.get("companies") or {}).get("name") or "").strip()
        title   = (r.get("title") or "").strip()
        if not co_name or not title:
            continue
        canon[r["id"]] = generate_job_fingerprint(title, co_name)

    # Group rows by canonical fingerprint.
    groups: dict = collections.defaultdict(list)
    for r in rows:
        if r["id"] in canon:
            groups[canon[r["id"]]].append(r)

    for cb_idx, (cfp, grp) in enumerate(groups.items()):
        if progress_callback and cb_idx % 50 == 0:
            progress_callback(f"Processing group {cb_idx}/{len(groups)}…", cb_idx / max(len(groups), 1))

        if len(grp) == 1:
            # No duplicates. If the stored fp differs from canonical, patch it.
            only = grp[0]
            if (only.get("fingerprint") or "") != cfp and not dry_run:
                try:
                    db._request("PATCH", f"jobs?id=eq.{only['id']}", json={"fingerprint": cfp})
                    stats["fingerprints_fixed"] += 1
                except Exception as e:
                    print(f"fp patch failed for {only['id'][:8]}: {e}")
            elif (only.get("fingerprint") or "") != cfp:
                stats["fingerprints_fixed"] += 1
            continue

        # Sub-group by normalized apply_url to separate true dupes from legit re-listings.
        stats["groups_with_dupes"] += 1
        by_url = collections.defaultdict(list)
        for r in grp:
            by_url[_normalize_apply_url(r.get("apply_url"))].append(r)

        # Merge source_boards across the WHOLE group so the winner row has the
        # full provenance list. Then within each apply_url sub-group, keep oldest.
        all_boards: set = set()
        for r in grp:
            sb = r.get("source_board") or ""
            sbs = (r.get("source_boards") or "").split(",")
            for b in [sb] + sbs:
                b = (b or "").strip()
                if b:
                    all_boards.add(b)

        for url_key, sub in by_url.items():
            # Sort oldest first using discovered_at as primary key.
            sub.sort(key=lambda r: (str(r.get("discovered_at") or "")))
            winner, losers = sub[0], sub[1:]

            if not dry_run:
                # Patch winner: canonical fingerprint + merged source_boards.
                try:
                    db._request("PATCH", f"jobs?id=eq.{winner['id']}", json={
                        "fingerprint":   cfp,
                        "source_boards": ",".join(sorted(all_boards)),
                    })
                    if (winner.get("fingerprint") or "") != cfp:
                        stats["fingerprints_fixed"] += 1
                except Exception as e:
                    print(f"winner patch failed for {winner['id'][:8]}: {e}")

                for loser in losers:
                    try:
                        db._request("DELETE", f"jobs?id=eq.{loser['id']}")
                        stats["rows_deleted"] += 1
                    except Exception as e:
                        print(f"delete failed for {loser['id'][:8]}: {e}")
            else:
                if (winner.get("fingerprint") or "") != cfp:
                    stats["fingerprints_fixed"] += 1
                stats["rows_deleted"] += len(losers)

    if progress_callback:
        progress_callback("Done", 1.0)
    return stats


_REJECT_PATTERNS = re.compile(
    r"("
    r"us\s+only|usa\s+only|united\s+states\s+only|u\.s\.\s+only"
    r"|us[- ]based\s+only|must\s+be\s+(in\s+the\s+us|authorized\s+to\s+work\s+in\s+the\s+u)"
    r"|us\s+citizens?\s+only|us\s+work\s+authorization\s+required"
    r"|uk\s+only|eu\s+only|canada\s+only|emea\s+only|apac\s+only"
    r")",
    re.IGNORECASE,
)

_INDIA_LOCATIONS = re.compile(
    r"\b("
    r"india|bangalore|bengaluru|hyderabad|mumbai|pune|chennai"
    r"|noida|gurgaon|gurugram|kolkata|delhi|ahmedabad|jaipur"
    r")\b",
    re.IGNORECASE,
)

_GLOBAL_ACCEPT = re.compile(
    r"("
    r"worldwide|anywhere|global(ly)?\s*remote|remote\s*[\-—]\s*worldwide"
    r"|remote\s*\(global\)|work\s+from\s+anywhere|fully\s+distributed"
    r"|remote\s*[\-—]\s*anywhere"
    r")",
    re.IGNORECASE,
)


def is_globally_remote(job: Dict) -> bool:
    """
    Returns True if the job is genuinely globally remote.
    Returns False for US-only, India-based, or region-locked roles.
    """
    location = (job.get("location") or "").strip()
    title = job.get("title") or ""
    description = job.get("description") or ""
    text = f"{location} {title} {description}"

    if _REJECT_PATTERNS.search(text):
        return False

    if _INDIA_LOCATIONS.search(location):
        return False

    if _GLOBAL_ACCEPT.search(text):
        return True

    loc_lower = location.lower().strip()
    # Blank or totally generic location — trust the is_remote flag
    if loc_lower in ("", "remote", "remote job", "unknown", "anywhere"):
        return bool(job.get("is_remote"))

    # Location is specific (city, country, "Remote - New York", etc.)
    # Only accept if GLOBAL_ACCEPT explicitly matched above; don't blindly trust is_remote.
    return False
