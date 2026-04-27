# job_scout/discovery/manual_seeds.py
# Moved from worker/discovery/manual_sources.py
"""Curated startup lists for manual import."""

YC_W24 = [
    {"name": "Airchat",  "website": "https://www.airchat.com",    "batch": "W24"},
    {"name": "Apex",     "website": "https://www.apex.ai",        "batch": "W24"},
    {"name": "Baselime", "website": "https://baselime.io",        "batch": "W24"},
    {"name": "Chroma",   "website": "https://www.trychroma.com",  "batch": "W24"},
    {"name": "Continue", "website": "https://continue.dev",       "batch": "W24"},
    {"name": "Dosu",     "website": "https://dosu.dev",           "batch": "W24"},
    {"name": "E2B",      "website": "https://e2b.dev",            "batch": "W24"},
    {"name": "Fable",    "website": "https://fable.com",          "batch": "W24"},
    {"name": "Giga ML",  "website": "https://gigaml.com",         "batch": "W24"},
    {"name": "Hona",     "website": "https://hona.ai",            "batch": "W24"},
]

AFRICA_STARTUPS = [
    {"name": "Wassha",       "website": "https://wassha.com",          "region": "africa", "notes": "Japanese company in Africa"},
    {"name": "Paystack",     "website": "https://paystack.com",        "region": "africa"},
    {"name": "Flutterwave",  "website": "https://flutterwave.com",     "region": "africa"},
    {"name": "Chipper Cash", "website": "https://chippercash.com",     "region": "africa"},
    {"name": "Andela",       "website": "https://andela.com",          "region": "africa"},
    {"name": "Kuda",         "website": "https://kuda.com",            "region": "africa"},
    {"name": "Wave",         "website": "https://wave.com",            "region": "africa"},
]


def get_manual_list(name: str) -> list:
    return {"yc_w24": YC_W24, "africa": AFRICA_STARTUPS}.get(name, [])
