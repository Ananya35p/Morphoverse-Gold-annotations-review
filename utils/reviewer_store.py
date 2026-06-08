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
    if isinstance(payload, dict):
        return payload

    try:
        from utils.storage_utils import load_review_from_supabase

        remote = load_review_from_supabase(username, poem_id)
        if isinstance(remote, dict):
            return remote
    except Exception:
        pass
    return None


def load_user_reviewed_index(username: str) -> Dict[str, Dict[str, Any]]:
    """Poems reviewed by this user only (local JSON + Supabase)."""
    index: Dict[str, Dict[str, Any]] = {}
    poems = load_user_submissions(username).get("poems") or {}
    for poem_id, payload in poems.items():
        if not isinstance(payload, dict):
            continue
        index[str(poem_id)] = {
            "poem_id": str(poem_id),
            "review_status": str(payload.get("review_status") or "reviewed"),
            "reviewed_at": payload.get("reviewed_at", ""),
        }

    try:
        from utils.storage_utils import load_reviewer_poem_ids_from_supabase, load_review_from_supabase

        for poem_id in load_reviewer_poem_ids_from_supabase(username):
            if poem_id in index:
                continue
            payload = load_review_from_supabase(username, poem_id)
            if isinstance(payload, dict):
                index[poem_id] = {
                    "poem_id": poem_id,
                    "review_status": str(payload.get("review_status") or "reviewed"),
                    "reviewed_at": payload.get("reviewed_at", ""),
                }
    except Exception:
        pass
    return index


def get_co_reviewers_for_poem(poem_id: str, exclude_username: str = "") -> List[str]:
    """Other reviewers who have already submitted this poem."""
    exclude = exclude_username.strip().lower()
    reviewers: List[str] = []

    ensure_submissions_dir()
    for path in sorted(SUBMISSIONS_DIR.glob("*.json")):
        try:
            record = load_json(path)
        except Exception:
            continue
        username = str(record.get("username") or path.stem)
        if username.lower() == exclude:
            continue
        poems = record.get("poems") or {}
        if poem_id in poems and isinstance(poems[poem_id], dict):
            reviewers.append(username)

    try:
        from utils.storage_utils import load_reviewer_ids_for_poem_from_supabase

        for name in load_reviewer_ids_for_poem_from_supabase(poem_id):
            if name.lower() != exclude and name not in reviewers:
                reviewers.append(name)
    except Exception:
        pass

    return sorted(reviewers)
