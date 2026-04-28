# job_scout/core/exceptions.py
"""Custom exceptions for Job Scout."""


class JobScoutError(Exception):
    """Base exception for all job-scout errors."""


class QuotaExceededError(JobScoutError):
    """Raised when an external API quota is exhausted."""

    def __init__(self, service: str, used: int, limit: int):
        self.service = service
        self.used = used
        self.limit = limit
        super().__init__(f"{service} quota exceeded: {used}/{limit}")


class ScraperError(JobScoutError):
    """Raised when a scraper fails to fetch data."""

    def __init__(self, source: str, reason: str):
        self.source = source
        super().__init__(f"Scraper error [{source}]: {reason}")


class ApplicationError(JobScoutError):
    """Raised when an auto-apply attempt fails."""

    def __init__(self, job_title: str, ats: str, reason: str):
        self.job_title = job_title
        self.ats = ats
        super().__init__(f"Application failed for '{job_title}' ({ats}): {reason}")


class ConfigError(JobScoutError):
    """Raised when required configuration is missing or invalid."""


class DBError(JobScoutError):
    """Raised when a database operation fails unrecoverably."""
