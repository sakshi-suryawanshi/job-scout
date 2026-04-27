# job_scout/scraping/boards/_rss.py
"""Generic RSS/Atom feed parser + all RSS-based board scrapers."""

import xml.etree.ElementTree as ET
from typing import List, Dict
from job_scout.scraping.base import clean_html, is_remote

_NS_ATOM = "http://www.w3.org/2005/Atom"


def parse_rss_feed(feed_url: str, source_board: str, limit: int = 80) -> List[Dict]:
    """Parse any standard RSS 2.0 or Atom feed for job listings."""
    import httpx
    try:
        client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
        response = client.get(feed_url)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        items = root.findall(".//item")
        if not items:
            items = root.findall(f".//{{{_NS_ATOM}}}entry")

        jobs = []
        for item in items[:limit]:
            def _t(tag):
                el = item.find(tag) or item.find(f"{{{_NS_ATOM}}}{tag}")
                return (el.text or "").strip() if el is not None else ""

            raw_title = _t("title")
            url = _t("link")
            if not url:
                link_el = item.find(f"{{{_NS_ATOM}}}link")
                if link_el is not None:
                    url = link_el.get("href", "")
            desc = clean_html(_t("description") or _t("summary") or _t("content"))

            company = "Unknown"
            job_title = raw_title
            for sep in (" at ", " @ ", " | ", " — ", " – "):
                if sep in raw_title:
                    parts = raw_title.rsplit(sep, 1)
                    if len(parts) == 2 and parts[1].strip():
                        job_title = parts[0].strip()
                        company = parts[1].strip()
                        break

            jobs.append({
                "title": job_title[:200],
                "company_name": company[:200],
                "location": "Remote" if is_remote("", raw_title, desc) else "Unknown",
                "is_remote": is_remote("", raw_title, desc),
                "apply_url": url,
                "description": desc[:5000],
                "source_board": source_board,
                "posted_at": _t("pubDate") or _t("published") or _t("updated") or None,
            })
        return jobs
    except Exception as e:
        print(f"{source_board} RSS error ({feed_url}): {e}")
        return []


# ---------------------------------------------------------------------------
# RSS-based boards (one-liners — each feeds parse_rss_feed)
# ---------------------------------------------------------------------------

class WeWorkRemotelyScraper:
    FEEDS = [
        "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
        "https://weworkremotely.com/remote-jobs.rss",
    ]

    def get_jobs(self) -> List[Dict]:
        import httpx
        client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
        seen_urls, jobs = set(), []

        for feed_url in self.FEEDS:
            try:
                response = client.get(feed_url)
                if response.status_code != 200:
                    continue
                root = ET.fromstring(response.content)
                for item in root.findall(".//item"):
                    title_el = item.find("title")
                    link_el = item.find("link")
                    desc_el = item.find("description")
                    if title_el is None or link_el is None:
                        continue
                    url = link_el.text.strip() if link_el.text else ""
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    raw_title = title_el.text or ""
                    description = clean_html(desc_el.text if desc_el is not None and desc_el.text else "")
                    if ":" in raw_title:
                        company_name, job_title = raw_title.split(":", 1)
                    else:
                        company_name, job_title = "Unknown", raw_title
                    jobs.append({
                        "title": job_title.strip(),
                        "company_name": company_name.strip(),
                        "location": "Remote",
                        "is_remote": True,
                        "apply_url": url,
                        "description": description[:5000],
                        "source_board": "weworkremotely",
                        "posted_at": None,
                    })
            except Exception as e:
                print(f"WWR feed error ({feed_url}): {e}")
        return jobs


class JobspressoScraper:
    def get_jobs(self, limit: int = 50) -> List[Dict]:
        import httpx
        try:
            client = httpx.Client(timeout=30, headers={"User-Agent": "JobScout/1.0"})
            response = client.get("https://jobspresso.co/feed/?post_type=job_listing")
            response.raise_for_status()
            root = ET.fromstring(response.content)
            jobs = []
            for item in root.findall(".//item")[:limit]:
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")
                date_el = item.find("pubDate")
                if title_el is None or link_el is None:
                    continue
                raw_title = title_el.text or ""
                url = link_el.text.strip() if link_el.text else ""
                description = clean_html(desc_el.text if desc_el is not None else "")
                company_name, job_title = "Unknown", raw_title
                if " at " in raw_title:
                    parts = raw_title.rsplit(" at ", 1)
                    job_title, company_name = parts[0].strip(), parts[1].strip()
                jobs.append({
                    "title": job_title[:200],
                    "company_name": company_name[:200],
                    "location": "Remote",
                    "is_remote": True,
                    "apply_url": url,
                    "description": description[:5000],
                    "source_board": "jobspresso",
                    "posted_at": date_el.text if date_el is not None else None,
                })
            return jobs
        except Exception as e:
            print(f"Jobspresso error: {e}")
            return []


class RemoteCo:
    def get_jobs(self): return parse_rss_feed("https://remote.co/remote-jobs/feed/", "remoteco")

class AuthenticJobsScraper:
    def get_jobs(self): return parse_rss_feed("https://authenticjobs.com/feed/", "authenticjobs")

class DjangoJobsScraper:
    def get_jobs(self): return parse_rss_feed("https://djangojobs.net/jobs/feed/rss/", "djangojobs")

class LaraJobsScraper:
    def get_jobs(self): return parse_rss_feed("https://larajobs.com/feed", "larajobs")

class NodeDeskScraper:
    def get_jobs(self): return parse_rss_feed("https://nodesk.co/remote-work/rss.xml", "nodesk")

class VueJobsScraper:
    def get_jobs(self): return parse_rss_feed("https://vuejobs.com/feed.atom", "vuejobs")

class GolangJobsScraper:
    def get_jobs(self): return parse_rss_feed("https://golangjobs.xyz/feed/", "golangjobs")

class DynamiteJobsScraper:
    def get_jobs(self): return parse_rss_feed("https://dynamitejobs.com/remote-jobs.rss", "dynamitejobs")

class SmashingMagJobsScraper:
    def get_jobs(self): return parse_rss_feed("https://jobs.smashingmagazine.com/jobs/rss", "smashingmag")

class FreshRemoteScraper:
    def get_jobs(self): return parse_rss_feed("https://freshremote.work/feed/", "freshremote")

class PowerToFlyScraper:
    def get_jobs(self): return parse_rss_feed("https://powertofly.com/jobs/feed/", "powertofly")

class WWRDevOpsScraper:
    def get_jobs(self):
        return parse_rss_feed(
            "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
            "weworkremotely",
        )

class WWRFrontendScraper:
    def get_jobs(self):
        return parse_rss_feed(
            "https://weworkremotely.com/categories/remote-front-end-programming-jobs.rss",
            "weworkremotely",
        )
