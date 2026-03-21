import json
import secrets
import sqlite3
from typing import Any

import streamlit as st


SESSION_QUERY_PARAM = "session"
_SESSION_TOKEN_STATE_KEY = "_browser_session_token"

PERSISTED_STATE_KEYS = (
    "admin_logged_in",
    "admin_quick_view",
    "admin_selected_candidate",
    "admin_selected_role",
    "allow_retest",
    "answer_audio_blobs",
    "answer_drafts",
    "answer_mode",
    "answers",
    "auth_view",
    "current_index",
    "dashboard_active_skill",
    "display_name",
    "experience",
    "interview_questions_meta",
    "interview_security_notice",
    "interview_submitted",
    "last_spoken_question_id",
    "logged_in",
    "results_saved",
    "results_summary",
    "role",
    "selected_primary_skill",
    "selected_specializations",
    "show_answer_review",
    "username",
)

_INT_KEYED_STATE_KEYS = {
    "answer_audio_blobs",
    "answer_drafts",
}


def ensure_browser_session_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS browser_sessions (
            session_token TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def _get_query_param_value(name: str) -> str | None:
    value = st.query_params.get(name)
    if isinstance(value, list):
        value = value[0] if value else None
    value = str(value or "").strip()
    return value or None


def get_session_token() -> str | None:
    token = st.session_state.get(_SESSION_TOKEN_STATE_KEY)
    if token:
        return str(token)

    token = _get_query_param_value(SESSION_QUERY_PARAM)
    if token:
        st.session_state[_SESSION_TOKEN_STATE_KEY] = token
    return token


def ensure_session_token() -> str:
    token = get_session_token()
    if token:
        return token

    token = secrets.token_urlsafe(32)
    st.session_state[_SESSION_TOKEN_STATE_KEY] = token
    return token


def set_session_query_param(token: str | None) -> None:
    if token:
        st.query_params[SESSION_QUERY_PARAM] = token
    elif SESSION_QUERY_PARAM in st.query_params:
        del st.query_params[SESSION_QUERY_PARAM]


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _json_safe(item_method())
        except Exception:
            pass

    return str(value)


def _restore_value(key: str, value: Any) -> Any:
    if key in _INT_KEYED_STATE_KEYS and isinstance(value, dict):
        restored = {}
        for item_key, item_value in value.items():
            try:
                restored[int(item_key)] = item_value
            except (TypeError, ValueError):
                restored[item_key] = item_value
        return restored

    return value


def restore_browser_session(conn: sqlite3.Connection) -> bool:
    ensure_browser_session_table(conn)

    if _SESSION_TOKEN_STATE_KEY in st.session_state:
        return False

    token = _get_query_param_value(SESSION_QUERY_PARAM)
    if not token:
        return False

    row = conn.execute(
        "SELECT state_json FROM browser_sessions WHERE session_token = ?",
        (token,),
    ).fetchone()

    if not row:
        set_session_query_param(None)
        return False

    try:
        state = json.loads(row[0])
    except json.JSONDecodeError:
        conn.execute("DELETE FROM browser_sessions WHERE session_token = ?", (token,))
        conn.commit()
        set_session_query_param(None)
        return False

    st.session_state[_SESSION_TOKEN_STATE_KEY] = token
    for key, value in state.items():
        st.session_state[key] = _restore_value(key, value)
    return True


def save_browser_session(conn: sqlite3.Connection) -> str | None:
    ensure_browser_session_table(conn)

    token = get_session_token()
    if not token:
        return None

    snapshot = {
        key: _json_safe(st.session_state[key])
        for key in PERSISTED_STATE_KEYS
        if key in st.session_state
    }
    conn.execute(
        """
        INSERT OR REPLACE INTO browser_sessions (session_token, state_json, updated_at)
        VALUES (?, ?, datetime('now'))
        """,
        (token, json.dumps(snapshot, ensure_ascii=True)),
    )
    conn.commit()
    return token


def clear_browser_session(conn: sqlite3.Connection) -> None:
    ensure_browser_session_table(conn)

    token = get_session_token()
    if token:
        conn.execute("DELETE FROM browser_sessions WHERE session_token = ?", (token,))
        conn.commit()

    st.session_state.pop(_SESSION_TOKEN_STATE_KEY, None)
    set_session_query_param(None)


def switch_page(page: str) -> None:
    token = get_session_token()
    if token:
        st.switch_page(page, query_params={SESSION_QUERY_PARAM: token})
    else:
        st.switch_page(page)
