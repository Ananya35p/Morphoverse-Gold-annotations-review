from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .io_utils import load_json, save_json, safe_reviewer_id


SUBMISSIONS_DIR = Path("reviewer_submissions")


def ensure_submissions_dir() -> None:
    SUBMISSIONS_DIR.mkdir(exist_ok=True)


def user_submission_path(username: str) -> Path:
    safe_name = safe_reviewer_id(username)
    return SUBMISSIONS_DIR / f"{safe_name}.json"


def empty_user_record(username: str, languages: List[str] | None = None) -> Dict[str, Any]:
    return {
        "username": username,
        "languages": languages or [],
        "poems": {},
    }


def load_user_submissions(username: str) -> Dict[str, Any]:
    ensure_submissions_dir()
    path = user_submission_path(username)
    if not path.exists():
        return empty_user_record(username)
    try:
        data = load_json(path)
    except Exception:
        return empty_user_record(username)
    data.setdefault("username", username)
    data.setdefault("languages", [])
    data.setdefault("poems", {})
    return data


def save_user_languages(username: str, languages: List[str]) -> None:
    record = load_user_submissions(username)
    record["languages"] = sorted(set(languages))
    save_json(user_submission_path(username), record)


def get_user_languages(username: str) -> List[str]:
    return list(load_user_submissions(username).get("languages") or [])


def save_poem_review(username: str, poem_id: str, payload: Dict[str, Any]) -> Path:
    """Store a poem review under the reviewer's username key."""
    ensure_submissions_dir()
    record = load_user_submissions(username)
    record["username"] = username
    poems = record.setdefault("poems", {})
    poems[poem_id] = payload
    path = user_submission_path(username)
    save_json(path, record)
    return path


def load_all_reviewer_submissions() -> List[Dict[str, Any]]:
    """Flatten all reviewer submissions for admin view."""
    ensure_submissions_dir()
    reviews: List[Dict[str, Any]] = []
    for path in sorted(SUBMISSIONS_DIR.glob("*.json")):
        try:
            record = load_json(path)
        except Exception:
            continue
        username = str(record.get("username") or path.stem)
        for poem_id, payload in (record.get("poems") or {}).items():
            if not isinstance(payload, dict):
                continue
            review = dict(payload)
            review["logged_in_user"] = username
            review["poem_id"] = review.get("poem_id") or poem_id
            review["_reviewer_file"] = str(path)
            review["_storage_source"] = "Reviewer store"
            reviews.append(review)
    return reviews


def load_user_poem_review(username: str, poem_id: str) -> Dict[str, Any] | None:
    poems = load_user_submissions(username).get("poems") or {}
    payload = poems.get(poem_id)
    return payload if isinstance(payload, dict) else None
