"""Auto-save reviewer annotation drafts."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Tuple

import pandas as pd
import streamlit as st

from .io_utils import now_iso, review_id
from .review_history import append_history_event
from .review_utils import get_original_poem, get_translation
from .review_utils import cleaned_records
from .reviewer_store import load_user_poem_review, save_poem_review


def _df_fingerprint(*dfs: pd.DataFrame) -> str:
    payload = []
    for df in dfs:
        if df is None or df.empty:
            payload.append([])
        else:
            payload.append(df.fillna("").to_dict(orient="records"))
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def build_draft_payload(
    *,
    username: str,
    poem_id: str,
    language: str,
    title: str,
    raw: Dict[str, Any],
    culture_df: pd.DataFrame,
    metaphor_df: pd.DataFrame,
    emotion_df: pd.DataFrame,
    motif_df: pd.DataFrame,
    previous: Dict[str, Any] | None,
) -> Dict[str, Any]:
    existing = dict(previous or {})
    payload: Dict[str, Any] = {
        "review_id": review_id(poem_id, username),
        "poem_id": poem_id,
        "language": language,
        "title": title,
        "review_status": "draft",
        "is_draft": True,
        "reviewer_id": username,
        "logged_in_user": username,
        "reviewer_confidence": existing.get("reviewer_confidence", "medium"),
        "reviewed_at": now_iso(),
        "original_poem": get_original_poem(raw),
        "english_translation": get_translation(raw),
        "source_annotation_file": raw.get("_source_file", ""),
        "final_annotations": {
            "culture_entities": cleaned_records(culture_df, "text"),
            "metaphor_spans": cleaned_records(metaphor_df, "source_text"),
            "stanza_emotions": cleaned_records(emotion_df, "stanza_index"),
            "visual_motifs": cleaned_records(motif_df, "motif"),
        },
        "review_changes": existing.get("review_changes") or {},
        "reviewer_decision": existing.get("reviewer_decision") or {"decision": "draft", "reason": ""},
        "raw_llm_annotation_snapshot": raw,
        "history": list(existing.get("history") or []),
        "last_autosave_at": now_iso(),
    }
    return payload


def maybe_autosave_draft(
    *,
    username: str,
    poem_id: str,
    language: str,
    title: str,
    raw: Dict[str, Any],
    culture_df: pd.DataFrame,
    metaphor_df: pd.DataFrame,
    emotion_df: pd.DataFrame,
    motif_df: pd.DataFrame,
    enabled: bool = True,
) -> Tuple[bool, str]:
    if not enabled:
        return False, ""

    fingerprint = _df_fingerprint(culture_df, metaphor_df, emotion_df, motif_df)
    state_key = f"autosave_fp_{username}_{poem_id}"
    if st.session_state.get(state_key) == fingerprint:
        previous = load_user_poem_review(username, poem_id)
        if previous and previous.get("last_autosave_at"):
            return False, str(previous.get("last_autosave_at"))
        return False, ""

    previous = load_user_poem_review(username, poem_id)
    payload = build_draft_payload(
        username=username,
        poem_id=poem_id,
        language=language,
        title=title,
        raw=raw,
        culture_df=culture_df,
        metaphor_df=metaphor_df,
        emotion_df=emotion_df,
        motif_df=motif_df,
        previous=previous,
    )
    append_history_event(payload, "draft_saved", note="Annotation tables auto-saved")
    save_poem_review(username, poem_id, payload)
    st.session_state[state_key] = fingerprint
    st.session_state[f"autosave_time_{username}_{poem_id}"] = payload["last_autosave_at"]
    return True, str(payload["last_autosave_at"])
