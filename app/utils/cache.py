"""
Simple file-based cache for parsed results.
Saves parsed resume/JD to disk so you don't re-parse during testing.
"""

import json
import os
import hashlib

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", ".cache")


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _hash_text(text: str) -> str:
    """Create a short hash of the input text for cache key."""
    return hashlib.md5(text.encode()).hexdigest()[:12]


def save_to_cache(key: str, data: dict):
    """Save data to cache file."""
    _ensure_cache_dir()
    filepath = os.path.join(CACHE_DIR, f"{key}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_from_cache(key: str) -> dict | None:
    """Load data from cache file. Returns None if not found."""
    filepath = os.path.join(CACHE_DIR, f"{key}.json")
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def get_resume_cache_key(resume_text: str) -> str:
    return f"resume_{_hash_text(resume_text)}"


def get_jd_cache_key(jd_text: str) -> str:
    return f"jd_{_hash_text(jd_text)}"


def cache_exists(key: str) -> bool:
    filepath = os.path.join(CACHE_DIR, f"{key}.json")
    return os.path.exists(filepath)