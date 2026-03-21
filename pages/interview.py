import datetime
import difflib
import hashlib
import io
import json
import re
import sqlite3
import base64
import time
import numpy as np
import speech_recognition as sr
import spacy
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from browser_session import restore_browser_session, save_browser_session, switch_page

st.set_page_config(page_title="Interview", layout="wide", initial_sidebar_state="collapsed")
st.markdown(
    """
<style>
[data-testid="stSidebarNav"] {display: none;}
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Roboto:wght@500;700&display=swap');

:root {
    --brand-primary: #0b4db6;
    --brand-primary-strong: #083a89;
    --brand-accent: #18a999;
    --text-primary: #12223a;
    --text-secondary: #334f72;
    --card-border: #dfe8f5;
}

html[data-theme="dark"] {
    --text-primary: #e8eefb;
    --text-secondary: #cedcf3;
    --card-border: #3d5273;
}

.status-box {
    background: linear-gradient(135deg, rgba(11, 77, 182, 0.08) 0%, rgba(24, 169, 153, 0.08) 100%);
    border: 1px solid var(--card-border);
    border-radius: 16px;
    box-shadow: 0 10px 26px rgba(12, 45, 95, 0.12);
    padding: 18px 20px;
    text-align: center;
    color: var(--text-primary);
}

html[data-theme="dark"] .status-box {
    background: linear-gradient(135deg, rgba(11, 77, 182, 0.18) 0%, rgba(24, 169, 153, 0.16) 100%);
}

.status-message {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0.02em;
}

html, body, [class*="css"] {
    font-family: "Inter", "Roboto", Arial, sans-serif;
    color: var(--text-primary);
}

h1, h2, h3, h4 {
    font-family: "Roboto", "Inter", Arial, sans-serif;
    color: var(--text-primary);
}

.main {
    background:
      radial-gradient(circle at 10% 12%, rgba(24, 169, 153, 0.08) 0%, rgba(24, 169, 153, 0) 34%),
      radial-gradient(circle at 85% 0%, rgba(11, 77, 182, 0.12) 0%, rgba(11, 77, 182, 0) 44%),
      linear-gradient(180deg, #f7faff 0%, #ffffff 70%);
}

html[data-theme="dark"] .main {
    background:
      radial-gradient(circle at 10% 12%, rgba(24, 169, 153, 0.18) 0%, rgba(24, 169, 153, 0) 34%),
      radial-gradient(circle at 85% 0%, rgba(11, 77, 182, 0.24) 0%, rgba(11, 77, 182, 0) 42%),
      linear-gradient(180deg, #0f172a 0%, #111827 72%);
}

.brand-bar {
    background: linear-gradient(135deg, var(--brand-primary) 0%, #2f8be6 100%);
    color: #fff;
    border-radius: 16px;
    padding: 14px 18px;
    margin-bottom: 12px;
    box-shadow: 0 10px 26px rgba(12, 45, 95, 0.16);
    display: flex;
    align-items: center;
    gap: 12px;
}

.brand-logo {
    width: 68px;
    height: 68px;
    border-radius: 18px;
    background: linear-gradient(145deg, #f9fcff 0%, #e7f1ff 58%, #d8e8ff 100%);
    border: 1px solid rgba(255, 255, 255, 0.8);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-family: "Roboto", Arial, sans-serif;
    line-height: 1;
    position: relative;
    overflow: hidden;
    box-shadow:
      0 12px 26px rgba(5, 28, 62, 0.3),
      inset 0 1px 0 rgba(255, 255, 255, 0.95),
      inset 0 -10px 18px rgba(103, 141, 192, 0.22);
}

.brand-logo::before {
    content: "";
    position: absolute;
    inset: 6px;
    border-radius: 12px;
    border: 1px solid rgba(25, 75, 146, 0.2);
    pointer-events: none;
}

.brand-logo::after {
    content: "";
    position: absolute;
    top: -18px;
    right: -22px;
    width: 56px;
    height: 56px;
    background: radial-gradient(circle, rgba(255, 255, 255, 0.85) 0%, rgba(255, 255, 255, 0) 72%);
    pointer-events: none;
}

.brand-main {
    font-size: 19px;
    letter-spacing: 0.08em;
    font-weight: 800;
    color: #0f3c7d;
    text-shadow: 0 1px 0 rgba(255, 255, 255, 0.45);
    z-index: 1;
}

.brand-inc {
    font-size: 8px;
    letter-spacing: 0.12em;
    margin-top: 5px;
    padding: 2px 6px;
    border-radius: 999px;
    background: rgba(16, 76, 157, 0.12);
    color: #1a4c93;
    border: 1px solid rgba(26, 76, 147, 0.2);
    font-weight: 700;
    z-index: 1;
}

.brand-title {
    font-size: 20px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-weight: 700;
    line-height: 1.1;
}

.brand-subtitle {
    font-size: 13px;
    margin-top: 4px;
    opacity: 0.95;
}

.sticky-quick-links {
    position: sticky;
    top: 10px;
    z-index: 20;
    background: rgba(255, 255, 255, 0.95);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    box-shadow: 0 8px 18px rgba(16, 43, 94, 0.08);
    padding: 8px 12px;
    margin-bottom: 12px;
    backdrop-filter: blur(8px);
}

html[data-theme="dark"] .sticky-quick-links {
    background: rgba(20, 33, 52, 0.9);
    border-color: var(--card-border);
    box-shadow: 0 8px 18px rgba(3, 10, 24, 0.4);
}

.sticky-quick-links a {
    text-decoration: none;
    color: var(--brand-primary);
    font-weight: 600;
    margin-right: 12px;
    font-size: 13px;
}

.summary-card {
    background: linear-gradient(115deg, #083a89 0%, #0b4db6 45%, #1a6fd1 100%);
    border-radius: 16px;
    color: #fff;
    padding: 14px 16px;
    margin-bottom: 12px;
    box-shadow: 0 10px 26px rgba(12, 45, 95, 0.14);
}

.summary-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
    margin-top: 10px;
}

.summary-item {
    background: rgba(255,255,255,0.15);
    border-radius: 10px;
    padding: 8px 10px;
}

.summary-label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    opacity: 0.92;
}

.summary-value {
    font-size: 16px;
    font-weight: 700;
    margin-top: 1px;
}

div[data-baseweb="segmented-control"] {
    background: transparent !important;
    border: 0 !important;
    padding: 0 !important;
}

div[data-baseweb="segmented-control"] label {
    min-width: 30px !important;
    padding: 0.18rem 0.55rem !important;
    border: 0 !important;
    box-shadow: none !important;
}

div[data-testid="stButton"] > button[kind="primary"] {
    background-color: #0b4db6;
    border: 1px solid #0b4db6;
    color: #ffffff;
}

div[data-testid="stButton"] > button[kind="primary"]:hover {
    background-color: #083a89;
    border: 1px solid #083a89;
    color: #ffffff;
}

[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] *,
[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] * {
    color: var(--text-secondary) !important;
    opacity: 1 !important;
}

[data-testid="stMetricValue"],
[data-testid="stMetricValue"] * {
    color: var(--text-primary) !important;
    opacity: 1 !important;
}

div[data-testid="stCheckbox"] label p,
div[data-testid="stRadio"] label p,
div[data-testid="stSelectbox"] label p,
div[data-testid="stTextInput"] label p,
div[data-testid="stTextArea"] label p {
    color: var(--text-primary) !important;
    opacity: 1 !important;
}

@media (max-width: 960px) {
    .summary-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .sticky-quick-links a {
        display: inline-block;
        margin-bottom: 6px;
    }
}
</style>
""",
    unsafe_allow_html=True,
)

# Database connection
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

restore_browser_session(conn)

TAB_SWITCH_QUERY_PARAM = "tab_violation"
TAB_SWITCH_EVENT_QUERY_PARAM = "tab_event"
TAB_SWITCH_BAN_REASON = "Switched tabs/apps during active interview."
TAB_SWITCH_BAN_MESSAGE = (
    "Interview locked because you switched tabs/apps during the active interview. Admin approval is required before another attempt."
)
INTERVIEW_TIME_LIMIT_SECONDS = 30 * 60


def ensure_security_schema():
    cursor.execute("PRAGMA table_info(candidate_profiles)")
    profile_columns = {row[1] for row in cursor.fetchall()}
    cursor.execute("PRAGMA table_info(interview_results)")
    interview_columns = {row[1] for row in cursor.fetchall()}

    if "is_banned" not in profile_columns:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0")
    if "ban_until" not in profile_columns:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN ban_until TEXT")
    if "ban_reason" not in profile_columns:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN ban_reason TEXT")
    if "created_at" not in profile_columns:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN created_at TEXT")
    if "interview_auth_status" not in profile_columns:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN interview_auth_status TEXT")
    if "interview_auth_updated_at" not in profile_columns:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN interview_auth_updated_at TEXT")

    if "created_at" not in interview_columns:
        cursor.execute("ALTER TABLE interview_results ADD COLUMN created_at TEXT")

    cursor.execute("UPDATE candidate_profiles SET created_at = datetime('now') WHERE created_at IS NULL OR created_at = ''")
    cursor.execute("UPDATE interview_results SET created_at = datetime('now') WHERE created_at IS NULL OR created_at = ''")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            reason TEXT,
            actor TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )

    conn.commit()


def reset_interview_progress_state():
    fixed_keys = (
        "role",
        "experience",
        "selected_primary_skill",
        "selected_specializations",
        "interview_questions",
        "interview_questions_meta",
        "answer_audio_blobs",
        "current_index",
        "answers",
        "answer_drafts",
        "interview_submitted",
        "results_summary",
        "results_saved",
        "answer_mode",
        "last_spoken_question_id",
        "interview_started_at_epoch",
        "interview_deadline_at_epoch",
        "allow_retest",
        "show_answer_review",
    )

    for key in fixed_keys:
        st.session_state.pop(key, None)

    dynamic_prefixes = ("ans_", "recorded_audio_", "processed_audio_digest_")
    for key in list(st.session_state.keys()):
        if key.startswith(dynamic_prefixes):
            del st.session_state[key]


def log_security_event(username, action, reason, actor="Interview Guard"):
    cursor.execute(
        """
        INSERT INTO admin_audit_log (username, action, reason, actor, created_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        """,
        (username, action, reason, actor),
    )
    conn.commit()


def _read_query_param(name):
    value = st.query_params.get(name)
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value or "").strip()


def _ensure_interview_timer():
    start_epoch = st.session_state.get("interview_started_at_epoch")
    deadline_epoch = st.session_state.get("interview_deadline_at_epoch")
    if isinstance(start_epoch, (int, float)) and isinstance(deadline_epoch, (int, float)) and deadline_epoch > start_epoch:
        return float(start_epoch), float(deadline_epoch)

    start_epoch = time.time()
    deadline_epoch = start_epoch + INTERVIEW_TIME_LIMIT_SECONDS
    st.session_state.interview_started_at_epoch = start_epoch
    st.session_state.interview_deadline_at_epoch = deadline_epoch
    return float(start_epoch), float(deadline_epoch)


def _get_remaining_interview_seconds(deadline_epoch):
    return max(0, int(deadline_epoch - time.time()))


def _sync_answer_drafts_from_widget_state():
    for key, value in list(st.session_state.items()):
        if not key.startswith("ans_"):
            continue
        suffix = key[4:]
        if suffix.isdigit():
            st.session_state.answer_drafts[int(suffix)] = str(value or "")


def render_interview_timer(deadline_epoch):
    components.html(
        f"""
        <div id="interview-timer-card" style="
            border: 1px solid #dfe8f5;
            border-radius: 16px;
            padding: 14px 18px;
            margin: 0 0 12px 0;
            background: linear-gradient(135deg, rgba(11, 77, 182, 0.08) 0%, rgba(24, 169, 153, 0.08) 100%);
            font-family: Inter, Roboto, Arial, sans-serif;
            color: #12223a;
            box-shadow: 0 10px 26px rgba(12, 45, 95, 0.12);
        ">
          <div style="font-size: 13px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.8;">
            Interview Timer
          </div>
          <div id="interview-timer-value" style="font-size: 30px; font-weight: 800; margin-top: 4px;">30:00</div>
          <div id="interview-timer-note" style="font-size: 13px; margin-top: 6px;">
            The interview will auto-submit on the next interaction after time expires.
          </div>
        </div>
        <script>
        (function () {{
            const deadlineEpoch = {json.dumps(float(deadline_epoch))};
            const valueNode = document.getElementById("interview-timer-value");
            const noteNode = document.getElementById("interview-timer-note");
            const cardNode = document.getElementById("interview-timer-card");

            function formatRemaining(totalSeconds) {{
                const safeSeconds = Math.max(0, totalSeconds);
                const minutes = Math.floor(safeSeconds / 60);
                const seconds = safeSeconds % 60;
                return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0");
            }}

            function render() {{
                const remaining = Math.max(0, Math.ceil(deadlineEpoch - (Date.now() / 1000)));
                valueNode.textContent = formatRemaining(remaining);

                if (remaining === 0) {{
                    cardNode.style.borderColor = "#c62828";
                    noteNode.textContent = "Time is up. Your interview will auto-submit on the next interaction.";
                    return;
                }}

                if (remaining <= 300) {{
                    cardNode.style.borderColor = "#d9822b";
                    noteNode.textContent = "Less than 5 minutes remaining.";
                    return;
                }}

                noteNode.textContent = "The interview will auto-submit on the next interaction after time expires.";
            }}

            render();
            const timerId = setInterval(function () {{
                render();
                if ((Date.now() / 1000) >= deadlineEpoch) {{
                    clearInterval(timerId);
                }}
            }}, 1000);
        }})();
        </script>
        """,
        height=118,
    )


def handle_tab_switch_violation_if_needed():
    violation_flag = _read_query_param(TAB_SWITCH_QUERY_PARAM)
    if not violation_flag:
        return

    username = str(st.session_state.get("username") or "").strip()
    if not username:
        for key in (TAB_SWITCH_QUERY_PARAM, TAB_SWITCH_EVENT_QUERY_PARAM):
            if key in st.query_params:
                del st.query_params[key]
        return

    event_name = _read_query_param(TAB_SWITCH_EVENT_QUERY_PARAM)
    event_detail_map = {
        "visibility_hidden": "Browser tab became hidden.",
        "window_blur": "Interview window lost focus.",
    }
    event_detail = event_detail_map.get(event_name, "").strip()
    reason = TAB_SWITCH_BAN_REASON if not event_detail else f"{TAB_SWITCH_BAN_REASON} {event_detail}"
    ban_until = (datetime.date.today() + datetime.timedelta(days=365)).isoformat()

    cursor.execute(
        """
        UPDATE candidate_profiles
        SET is_banned = 1,
            ban_until = ?,
            ban_reason = ?,
            interview_auth_status = 'pending',
            interview_auth_updated_at = datetime('now')
        WHERE id = (
            SELECT id
            FROM candidate_profiles
            WHERE username = ?
            ORDER BY id DESC
            LIMIT 1
        )
        """,
        (ban_until, reason, username),
    )
    conn.commit()
    log_security_event(username, "TAB_SWITCH_BAN", reason)
    reset_interview_progress_state()
    st.session_state["interview_security_notice"] = TAB_SWITCH_BAN_MESSAGE
    save_browser_session(conn)
    switch_page("login.py")


ensure_security_schema()
handle_tab_switch_violation_if_needed()

required_session_keys = ("username", "role", "experience")
if any(key not in st.session_state for key in required_session_keys):
    st.error("Please login and submit candidate details before starting the interview.")
    if st.button("Go to Login"):
        switch_page("login.py")
    st.stop()

username = st.session_state.username
display_name = st.session_state.get("display_name") or username
role = st.session_state.role
experience = st.session_state.experience

if "current_index" not in st.session_state:
    st.session_state.current_index = 0
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "answer_drafts" not in st.session_state:
    st.session_state.answer_drafts = {}
if "answer_audio_blobs" not in st.session_state:
    st.session_state.answer_audio_blobs = {}
if "interview_submitted" not in st.session_state:
    st.session_state.interview_submitted = False
if "results_summary" not in st.session_state:
    st.session_state.results_summary = None
if "results_saved" not in st.session_state:
    st.session_state.results_saved = False
if "answer_mode" not in st.session_state:
    st.session_state.answer_mode = "Speech"
if "last_spoken_question_id" not in st.session_state:
    st.session_state.last_spoken_question_id = None
if "allow_retest" not in st.session_state:
    st.session_state.allow_retest = False
if "show_answer_review" not in st.session_state:
    st.session_state.show_answer_review = False


@st.cache_resource
def load_nlp_model():
    return spacy.load("en_core_web_md")


@st.cache_data
def load_intents():
    with open("intents.json", "r", encoding="utf-8") as file:
        return json.load(file)


def get_nlp_model():
    return load_nlp_model()


INTENTS = load_intents()


# --- Helper functions ---
def _normalize_text(value):
    return str(value or "").strip().lower()


def _normalize_list(values):
    normalized = []
    for value in values or []:
        cleaned = _normalize_text(value)
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def clean_question_text(question_text, role_hint="", experience_hint=""):
    text = str(question_text or "").strip()
    if not text:
        return ""

    first_clause = text.split(",", 1)[0].strip()
    first_clause_lower = _normalize_text(first_clause)

    has_role_experience_prefix = (
        first_clause_lower.startswith("as a ")
        or first_clause_lower.startswith("as an ")
        or (
            (first_clause_lower.startswith("for a ") or first_clause_lower.startswith("for an "))
            and "(" in first_clause
            and ")" in first_clause
        )
        or (
            (first_clause_lower.startswith("in a ") or first_clause_lower.startswith("in an "))
            and "(" in first_clause
            and ")" in first_clause
        )
    )

    role_hint_normalized = _normalize_text(role_hint)
    experience_hint_normalized = _normalize_text(experience_hint)
    if role_hint_normalized and role_hint_normalized in first_clause_lower:
        has_role_experience_prefix = True
    if experience_hint_normalized and experience_hint_normalized in first_clause_lower:
        has_role_experience_prefix = True

    if has_role_experience_prefix and "," in text:
        text = text.split(",", 1)[1].strip()

    return text[0].upper() + text[1:] if text else text


def get_display_question_text(question):
    return clean_question_text(
        question.get("question", ""),
        question.get("role", ""),
        question.get("experience", ""),
    )


def _question_key_from_text(question_text):
    return _normalize_text(clean_question_text(question_text))


def _normalize_similarity_text(value):
    cleaned = _normalize_text(value)
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _sequence_similarity(text_a, text_b):
    if not text_a or not text_b:
        return 0.0
    return float(difflib.SequenceMatcher(None, text_a, text_b).ratio())


def _question_uid(question):
    return "|".join(
        [
            _normalize_text(question.get("role", "")),
            _normalize_text(question.get("experience", "")),
            _normalize_text(question.get("difficulty", "")),
            _normalize_text(question.get("skill", "")),
            _normalize_text(question.get("specialization", "")),
            _normalize_text(question.get("question", "")),
        ]
    )


def _difficulty_quotas(experience, total_questions):
    total = max(int(total_questions), 1)
    normalized_experience = _normalize_text(experience)

    if normalized_experience == "fresher":
        preferred = [("easy", 10), ("hard", 5)]
    elif normalized_experience in ("1-3 years", "4-10 years"):
        preferred = [("moderate", 10), ("hard", 5)]
    else:
        preferred = [("moderate", 10), ("hard", 5)]

    quotas = {"easy": 0, "moderate": 0, "hard": 0}
    remaining = total

    for difficulty, target in preferred:
        take = min(target, remaining)
        quotas[difficulty] = take
        remaining -= take

    if remaining > 0:
        fill_order = [difficulty for difficulty, _ in preferred]
        for difficulty in ["easy", "moderate", "hard"]:
            if difficulty not in fill_order:
                fill_order.append(difficulty)

        index = 0
        while remaining > 0:
            quotas[fill_order[index % len(fill_order)]] += 1
            remaining -= 1
            index += 1

    return quotas


def get_questions(role, experience, selected_skill="", selected_specializations=None, total_questions=15):
    """Select questions based on role, experience, selected skill, and specializations."""
    role_pool = [q for q in INTENTS if q.get("role") == role and q.get("experience") == experience]
    if not role_pool:
        return []

    normalized_skill = _normalize_text(selected_skill)
    normalized_specializations = set(_normalize_list(selected_specializations))
    strict_specialization_mode = bool(normalized_skill and normalized_specializations)

    exact_specialization_matches = []
    selected_skill_matches = []
    fallback_matches = []

    for question in role_pool:
        q_skill = _normalize_text(question.get("skill", ""))
        q_specialization = _normalize_text(question.get("specialization", ""))

        if normalized_skill:
            if q_skill != normalized_skill:
                if strict_specialization_mode:
                    continue
                fallback_matches.append(question)
                continue

            if strict_specialization_mode:
                if q_specialization and q_specialization in normalized_specializations:
                    exact_specialization_matches.append(question)
                elif not q_specialization:
                    selected_skill_matches.append(question)
                else:
                    continue
            else:
                if q_specialization and q_specialization in normalized_specializations:
                    exact_specialization_matches.append(question)
                else:
                    selected_skill_matches.append(question)
        else:
            fallback_matches.append(question)

    prioritized = role_pool
    if normalized_skill:
        prioritized = exact_specialization_matches + selected_skill_matches
        if not strict_specialization_mode:
            prioritized += fallback_matches

    ordered_questions = []
    seen_ids = set()
    for question in prioritized:
        question_id = _question_uid(question)
        if question_id not in seen_ids:
            seen_ids.add(question_id)
            ordered_questions.append(question)

    max_questions = min(max(int(total_questions), 1), len(ordered_questions))
    quotas = _difficulty_quotas(experience, max_questions)

    selected_questions = []
    selected_ids = set()
    selected_counts = {"easy": 0, "moderate": 0, "hard": 0}

    for difficulty in ["easy", "moderate", "hard"]:
        quota = quotas[difficulty]
        if quota <= 0:
            continue
        for question in ordered_questions:
            if selected_counts[difficulty] >= quota:
                break

            question_id = _question_uid(question)
            if question_id in selected_ids:
                continue

            question_difficulty = _normalize_text(question.get("difficulty", ""))
            if difficulty == "moderate":
                if question_difficulty not in ("moderate", "medium"):
                    continue
            elif question_difficulty != difficulty:
                continue

            selected_questions.append(question)
            selected_ids.add(question_id)
            selected_counts[difficulty] += 1

    for question in ordered_questions:
        if len(selected_questions) >= max_questions:
            break

        question_id = _question_uid(question)
        if question_id in selected_ids:
            continue

        selected_questions.append(question)
        selected_ids.add(question_id)

    return selected_questions[:max_questions]


def speak_question_text(question_id, question_text, force=False):
    """Speak question text using browser speech synthesis."""
    if not question_text:
        return

    if not force and st.session_state.get("last_spoken_question_id") == question_id:
        return

    spoken_text = json.dumps(str(question_text))
    components.html(
        f"""
        <script>
        const text = {spoken_text};
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        utterance.volume = 1.0;

        const intro = new SpeechSynthesisUtterance("Question");
        intro.rate = 1.0;
        intro.pitch = 1.0;
        intro.volume = 0.4;

        const speakMain = () => window.speechSynthesis.speak(utterance);

        window.speechSynthesis.cancel();
        window.speechSynthesis.resume();

        intro.onend = () => setTimeout(speakMain, 80);

        setTimeout(() => {{
            if (window.speechSynthesis.getVoices().length === 0) {{
                window.speechSynthesis.onvoiceschanged = () => {{
                    window.speechSynthesis.onvoiceschanged = null;
                    window.speechSynthesis.speak(intro);
                }};
            }} else {{
                window.speechSynthesis.speak(intro);
            }}
        }}, 180);
        </script>
        """,
        height=0,
    )
    st.session_state.last_spoken_question_id = question_id


def listen_for_answer(timeout=None, phrase_time_limit=None, ambient_duration=2):
    """Capture voice answer from microphone and transcribe via Google Speech Recognition."""
    recognizer = sr.Recognizer()

    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=ambient_duration)
        audio = recognizer.listen(
            source,
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
        )

    return recognizer.recognize_google(audio)


def transcribe_uploaded_audio(recorded_audio):
    """Transcribe audio captured from st.audio_input (Done-button workflow)."""
    audio_bytes = recorded_audio.getvalue() if recorded_audio else b""
    if not audio_bytes:
        return "", ""

    digest = hashlib.sha1(audio_bytes).hexdigest()
    recognizer = sr.Recognizer()

    with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
        audio = recognizer.record(source)

    transcript = recognizer.recognize_google(audio)
    return transcript, digest


def encode_audio_blob(audio_bytes):
    if not audio_bytes:
        return ""
    return base64.b64encode(audio_bytes).decode("ascii")


def decode_audio_blob(audio_base64):
    if not audio_base64:
        return b""
    try:
        return base64.b64decode(audio_base64)
    except (ValueError, TypeError):
        return b""


def inject_answer_security_guards():
    components.html(
        """
        <script>
        (function () {
            const win = window.parent;
            const doc = win.document;
            if (!doc || doc.__interviewSecurityGuardsApplied) {
                return;
            }
            doc.__interviewSecurityGuardsApplied = true;
            const TAB_VIOLATION_PARAM = __TAB_VIOLATION_PARAM__;

            const isInterviewPage = function () {
                const title = String((win.document && win.document.title) || "").toLowerCase();
                return title.includes("interview");
            };

            const blockEvent = function (event) {
                if (!isInterviewPage()) {
                    return true;
                }
                event.preventDefault();
                event.stopPropagation();
                return false;
            };

            const triggerViolation = function (reason) {
                if (!isInterviewPage() || win.__interviewTabViolationTriggered) {
                    return;
                }

                try {
                    win.__interviewTabViolationTriggered = true;
                    const url = new URL(win.location.href);
                    url.searchParams.set(TAB_VIOLATION_PARAM, "1");
                    url.searchParams.set("tab_event", reason);
                    win.location.replace(url.toString());
                } catch (error) {
                    console.error("Interview tab-switch guard failed", error);
                }
            };

            ["copy", "cut", "paste", "contextmenu", "dragstart", "drop"].forEach(function (name) {
                doc.addEventListener(name, blockEvent, true);
            });

            doc.addEventListener(
                "keydown",
                function (event) {
                    if (!isInterviewPage()) {
                        return true;
                    }
                    const key = (event.key || "").toLowerCase();
                    const blocked = ["c", "v", "x", "u", "s", "p"];
                    if ((event.ctrlKey || event.metaKey) && blocked.includes(key)) {
                        event.preventDefault();
                        event.stopPropagation();
                        return false;
                    }
                    return true;
                },
                true
            );

            doc.addEventListener(
                "visibilitychange",
                function () {
                    if (doc.visibilityState === "hidden") {
                        triggerViolation("visibility_hidden");
                    }
                },
                true
            );

            win.addEventListener(
                "blur",
                function () {
                    win.setTimeout(function () {
                        if (doc.visibilityState === "hidden") {
                            triggerViolation("window_blur");
                        }
                    }, 50);
                },
                true
            );
        })();
        </script>
        """
        .replace("__TAB_VIOLATION_PARAM__", json.dumps(TAB_SWITCH_QUERY_PARAM)),
        height=0,
    )


def extract_keywords(answer):
    """Extract normalized keywords using spaCy."""
    nlp_model = get_nlp_model()
    doc = nlp_model(answer)
    return [token.lemma_.lower() for token in doc if token.is_alpha and not token.is_stop]


def infer_topic(question):
    topic = question.get("topic", "")
    if isinstance(topic, str) and topic.strip():
        return topic.strip()
    keywords = question.get("keywords", [])
    if keywords:
        return str(keywords[0]).strip().title()
    return "General"


def empty_evaluation_result():
    return {
        "result_label": "Incorrect",
        "relevance_score": 0.0,
        "confidence_score": 0.0,
        "matched_keywords": [],
        "missing_keywords": [],
        "coverage_score": 0.0,
        "semantic_similarity_score": 0.0,
        "length_quality_score": 0.0,
        "signal_agreement_score": 0.0,
        "boundary_margin_score": 0.0,
        "evidence_strength_score": 0.0,
        "improvement_insights": ["Answer was empty. Add a complete response with technical details."],
    }


def empty_policy_result():
    return {
        "ai_risk_score": 0.0,
        "plagiarism_score": 0.0,
        "ai_flag": False,
        "plagiarism_flag": False,
        "ai_signal_count": 0,
        "ai_strong_signal_count": 0,
        "ai_decision_rule": "",
        "ai_signal_breakdown": {},
        "violation_flags": [],
        "violation_remark": "",
    }


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def evaluate_answer(answer, expected_keywords, reference_text=""):
    """Return label, scores, keyword diagnostics, and per-answer improvement guidance."""
    answer_text = (answer or "").strip()
    if not answer_text:
        return empty_evaluation_result()

    normalized_expected = []
    for keyword in expected_keywords:
        if isinstance(keyword, str):
            cleaned = keyword.strip().lower()
            if cleaned and cleaned not in normalized_expected:
                normalized_expected.append(cleaned)

    if not normalized_expected:
        return empty_evaluation_result()

    nlp_model = get_nlp_model()
    doc = nlp_model(answer_text)
    answer_lower = answer_text.lower()
    extracted_lemmas = set(extract_keywords(answer_text))
    content_tokens = [token for token in doc if token.is_alpha and not token.is_stop]

    matched_keywords = []
    missing_keywords = []
    keyword_similarity_scores = []

    for keyword in normalized_expected:
        keyword_doc = nlp_model(keyword)
        keyword_lemmas = [token.lemma_.lower() for token in keyword_doc if token.is_alpha and not token.is_stop]

        direct_phrase_match = keyword in answer_lower
        lemma_match = bool(keyword_lemmas) and all(lemma in extracted_lemmas for lemma in keyword_lemmas)

        doc_similarity = 0.0
        if doc.vector_norm and keyword_doc.vector_norm:
            doc_similarity = float(doc.similarity(keyword_doc))

        token_similarity = 0.0
        for token in content_tokens:
            if not token.has_vector or not token.vector_norm:
                continue
            for key_token in keyword_doc:
                if not key_token.is_alpha or not key_token.has_vector or not key_token.vector_norm:
                    continue
                token_similarity = max(token_similarity, float(token.similarity(key_token)))

        best_similarity = max(doc_similarity, token_similarity)
        semantic_match = best_similarity >= 0.72
        keyword_similarity_scores.append(best_similarity)

        if direct_phrase_match or lemma_match or semantic_match:
            matched_keywords.append(keyword)
        else:
            missing_keywords.append(keyword)

    coverage = len(matched_keywords) / len(normalized_expected)
    reference = (reference_text or "").strip() or " ".join(normalized_expected)

    semantic_similarity = 0.0
    if reference:
        reference_doc = nlp_model(reference)
        if doc.vector_norm and reference_doc.vector_norm:
            semantic_similarity = float(doc.similarity(reference_doc))
        elif keyword_similarity_scores:
            semantic_similarity = float(sum(keyword_similarity_scores) / len(keyword_similarity_scores))

    min_tokens = 12
    length_quality = _clamp(len(content_tokens) / min_tokens)

    relevance_score = 100 * (
        0.55 * coverage +
        0.30 * _clamp(semantic_similarity) +
        0.15 * length_quality
    )
    relevance_score = _clamp(relevance_score / 100, 0, 1) * 100

    coverage_percent = coverage * 100
    if coverage_percent >= 85:
        result_label = "Correct"
    elif coverage_percent < 20:
        result_label = "Incorrect"
    else:
        result_label = "Partially Correct"

    signal_agreement = _clamp(1 - abs(coverage - _clamp(semantic_similarity)))
    nearest_boundary = min(abs(relevance_score - 45), abs(relevance_score - 75))
    boundary_margin = _clamp(nearest_boundary / 30)
    evidence_strength = _clamp((0.7 * coverage) + (0.3 * length_quality))

    confidence_score = 100 * (
        0.45 * signal_agreement +
        0.35 * boundary_margin +
        0.20 * evidence_strength
    )

    if len(content_tokens) < 4:
        confidence_score = min(confidence_score, 35.0)

    confidence_score = _clamp(confidence_score / 100, 0, 1) * 100

    improvement_insights = []
    if missing_keywords:
        improvement_insights.append("Add these key concepts: " + ", ".join(missing_keywords[:3]) + ".")
    if _clamp(semantic_similarity) < 0.55:
        improvement_insights.append("Align the answer more directly to the asked concept and scenario.")
    if len(content_tokens) < min_tokens:
        improvement_insights.append("Increase depth with at least one concrete example or use-case.")
    if confidence_score < 55:
        improvement_insights.append("Use a clearer structure: definition, mechanism, and practical impact.")
    if not improvement_insights and result_label == "Correct":
        improvement_insights.append("Solid answer. Add one practical production example to make it stronger.")

    return {
        "result_label": result_label,
        "relevance_score": round(relevance_score, 1),
        "confidence_score": round(confidence_score, 1),
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "coverage_score": round(coverage * 100, 1),
        "semantic_similarity_score": round(_clamp(semantic_similarity) * 100, 1),
        "length_quality_score": round(length_quality * 100, 1),
        "signal_agreement_score": round(signal_agreement * 100, 1),
        "boundary_margin_score": round(boundary_margin * 100, 1),
        "evidence_strength_score": round(evidence_strength * 100, 1),
        "improvement_insights": improvement_insights[:4],
    }


AI_DIRECT_PHRASES = (
    "as an ai",
    "as an ai language model",
    "as a ai language model",
    "as ai language model",
    "as an ai model",
    "as a large language model",
    "as a virtual assistant",
    "i am an ai language model",
    "i'm an ai language model",
    "i am a large language model",
    "i'm a large language model",
    "i cannot provide",
    "i do not have personal",
    "i cannot access real-time",
    "i don't have personal experiences",
    "i do not have real-time access",
)

AI_STYLE_PHRASES = (
    "in conclusion",
    "to summarize",
    "in summary",
    "additionally",
    "moreover",
    "furthermore",
    "it is worth noting that",
    "it is important to note",
    "in this context",
    "overall,",
    "on the other hand",
)

AI_SIGNAL_LABELS = {
    "direct_ai_disclaimer": "Direct AI-disclaimer phrase",
    "template_style_density": "Template-style transition density",
    "low_lexical_diversity": "Low lexical diversity",
    "very_low_lexical_diversity": "Very low lexical diversity",
    "uniform_sentence_structure": "Over-uniform sentence structure",
    "repeated_sentence_starters": "Repeated sentence starters",
    "repeated_phrase_pattern": "Repeated phrase patterns",
    "mild_repeated_phrase_pattern": "Mild repeated phrase patterns",
    "low_specificity_content": "Low specificity content",
    "keyword_stuffing_pattern": "Keyword stuffing pattern",
    "over_polished_low_specificity": "Over-polished but low-specificity answer",
}


AI_DIRECT_REGEX_PATTERNS = (
    re.compile(r"\bas\s+(?:an?\s+)?a\s*i(?:\s+language)?\s+model\b"),
    re.compile(r"\bi\s*(?:am|'m)\s+(?:an?\s+)?a\s*i(?:\s+language)?\s+model\b"),
    re.compile(r"\bas\s+(?:a\s+)?large\s+language\s+model\b"),
    re.compile(r"\bi\s*(?:am|'m)\s+(?:a\s+)?large\s+language\s+model\b"),
    re.compile(r"\bi\s+(?:can(?:not|'t)|do\s+not|don't)\s+(?:provide|access)\b.*\b(?:real\s*time|personal)\b"),
)


def _find_direct_ai_hits(lowered_answer, normalized_answer):
    hits = []

    for phrase in AI_DIRECT_PHRASES:
        if phrase in lowered_answer:
            hits.append(phrase)

    for phrase in AI_DIRECT_PHRASES:
        normalized_phrase = _normalize_similarity_text(phrase)
        if normalized_phrase and normalized_phrase in normalized_answer and phrase not in hits:
            hits.append(phrase)

    for pattern in AI_DIRECT_REGEX_PATTERNS:
        if pattern.search(lowered_answer):
            regex_label = f"regex:{pattern.pattern}"
            if regex_label not in hits:
                hits.append(regex_label)

    return hits


def _find_style_ai_hits(lowered_answer, normalized_answer):
    hits = []

    for phrase in AI_STYLE_PHRASES:
        if phrase in lowered_answer:
            hits.append(phrase)
            continue

        normalized_phrase = _normalize_similarity_text(phrase)
        if normalized_phrase and normalized_phrase in normalized_answer:
            hits.append(phrase)

    deduped = []
    for phrase in hits:
        if phrase not in deduped:
            deduped.append(phrase)
    return deduped


def build_historical_answer_index(exclude_username):
    cursor.execute(
        """
        SELECT username, original_answers
        FROM interview_results
        WHERE original_answers IS NOT NULL
          AND username <> ?
        """,
        (exclude_username,),
    )
    rows = cursor.fetchall()

    historical_index = {}
    for _, raw_answers in rows:
        if not raw_answers:
            continue

        try:
            parsed = json.loads(raw_answers)
        except (TypeError, json.JSONDecodeError):
            continue

        if not isinstance(parsed, list):
            continue

        for item in parsed:
            if not isinstance(item, dict):
                continue
            question_text = _question_key_from_text(item.get("question_text", ""))
            answer_text = str(item.get("answer_text", "") or "").strip()
            if not question_text or not answer_text:
                continue
            historical_index.setdefault(question_text, []).append(answer_text)

    return historical_index


def _repeated_ngram_ratio(tokens, n=4):
    if len(tokens) < (n * 2):
        return 0.0

    ngrams = [tuple(tokens[idx:idx + n]) for idx in range(len(tokens) - n + 1)]
    if not ngrams:
        return 0.0

    counts = {}
    for ngram in ngrams:
        counts[ngram] = counts.get(ngram, 0) + 1

    repeated = sum((count - 1) for count in counts.values() if count > 1)
    return repeated / max(len(ngrams), 1)


def _sentence_starter_repetition(doc):
    starters = []
    for sentence in doc.sents:
        words = [token.lemma_.lower() for token in sentence if token.is_alpha]
        if words:
            starters.append(" ".join(words[:2]))

    if len(starters) < 3:
        return 0.0

    counts = {}
    for starter in starters:
        counts[starter] = counts.get(starter, 0) + 1
    return max(counts.values()) / max(len(starters), 1)


def _specificity_ratio(doc):
    alpha_tokens = [token for token in doc if token.is_alpha]
    if not alpha_tokens:
        return 0.0

    specific_tokens = 0
    for token in alpha_tokens:
        is_entity = bool(token.ent_type_) and token.ent_type_ not in {"CARDINAL", "ORDINAL"}
        is_specific = token.like_num or token.pos_ == "PROPN" or is_entity
        if is_specific:
            specific_tokens += 1

    return specific_tokens / len(alpha_tokens)


def compute_ai_risk_signals(cleaned_answer, answer_tokens, doc, evaluation, direct_ai_hits, style_ai_hits):
    word_count = len(answer_tokens)
    lexical_diversity = len(set(answer_tokens)) / max(word_count, 1)
    sentence_lengths = [len([token for token in sentence if token.is_alpha]) for sentence in doc.sents]
    sentence_count = len(sentence_lengths)
    avg_sentence_length = (sum(sentence_lengths) / sentence_count) if sentence_count else float(word_count)
    sentence_std = float(np.std(sentence_lengths)) if sentence_lengths else 0.0
    sentence_uniformity = (sentence_std / max(avg_sentence_length, 1.0)) if sentence_count else 0.0
    style_density = len(style_ai_hits) / max(sentence_count, 1)
    repeated_4gram_ratio = _repeated_ngram_ratio(answer_tokens, n=4)
    starter_repetition = _sentence_starter_repetition(doc)
    specificity_ratio = _specificity_ratio(doc)

    matched_keywords = evaluation.get("matched_keywords", [])
    keyword_density = len(matched_keywords) / max(word_count, 1)

    signal_points = []

    if direct_ai_hits:
        signal_points.append(("direct_ai_disclaimer", 95.0))

    if len(style_ai_hits) >= 2 and style_density >= 0.34:
        signal_points.append(("template_style_density", 18.0))

    if word_count >= 40 and lexical_diversity < 0.38:
        signal_points.append(("low_lexical_diversity", 16.0))

    if word_count >= 70 and lexical_diversity < 0.34:
        signal_points.append(("very_low_lexical_diversity", 10.0))

    if sentence_count >= 4 and avg_sentence_length >= 14 and sentence_uniformity < 0.25:
        signal_points.append(("uniform_sentence_structure", 14.0))

    if sentence_count >= 4 and starter_repetition >= 0.60:
        signal_points.append(("repeated_sentence_starters", 14.0))

    if repeated_4gram_ratio >= 0.14:
        signal_points.append(("repeated_phrase_pattern", 20.0))
    elif repeated_4gram_ratio >= 0.08:
        signal_points.append(("mild_repeated_phrase_pattern", 10.0))

    if word_count >= 55 and specificity_ratio < 0.03:
        signal_points.append(("low_specificity_content", 12.0))

    if len(matched_keywords) >= 8 and keyword_density > 0.18:
        signal_points.append(("keyword_stuffing_pattern", 14.0))

    if (
        _safe_float(evaluation.get("relevance_score"), 0.0) >= 92.0
        and _safe_float(evaluation.get("confidence_score"), 0.0) >= 80.0
        and word_count >= 45
        and specificity_ratio < 0.05
    ):
        signal_points.append(("over_polished_low_specificity", 12.0))

    ai_risk = min(100.0, sum(points for _, points in signal_points))
    total_signal_count = len(signal_points)
    strong_signal_count = sum(1 for _, points in signal_points if points >= 12.0)

    ai_flag = False
    ai_decision_rule = "No strong AI pattern detected."
    if direct_ai_hits:
        ai_flag = True
        ai_decision_rule = "Flagged due to direct AI-disclaimer phrase."
    elif ai_risk >= 88.0:
        ai_flag = True
        ai_decision_rule = "Flagged because AI risk score reached severe threshold (>= 88)."
    elif ai_risk >= 78.0 and strong_signal_count >= 2:
        ai_flag = True
        ai_decision_rule = "Flagged because AI risk is high (>= 78) with at least two strong signals."

    breakdown = {
        "word_count": word_count,
        "lexical_diversity": round(float(lexical_diversity), 4),
        "style_phrase_hit_count": len(style_ai_hits),
        "style_density": round(float(style_density), 4),
        "sentence_count": sentence_count,
        "avg_sentence_length": round(float(avg_sentence_length), 2),
        "sentence_uniformity": round(float(sentence_uniformity), 4),
        "repeated_4gram_ratio": round(float(repeated_4gram_ratio), 4),
        "starter_repetition": round(float(starter_repetition), 4),
        "specificity_ratio": round(float(specificity_ratio), 4),
        "keyword_density": round(float(keyword_density), 4),
        "total_signal_count": int(total_signal_count),
        "strong_signal_count": int(strong_signal_count),
        "signals_triggered": [name for name, _ in signal_points],
        "signal_weights": {name: points for name, points in signal_points},
        "signal_labels": {
            name: AI_SIGNAL_LABELS.get(name, name.replace("_", " ").strip().title())
            for name, _ in signal_points
        },
        "direct_phrase_hits": direct_ai_hits[:5],
        "style_phrase_hits": style_ai_hits[:5],
        "decision_rule": ai_decision_rule,
    }

    return (
        round(float(ai_risk), 1),
        bool(ai_flag),
        int(total_signal_count),
        int(strong_signal_count),
        ai_decision_rule,
        breakdown,
    )


def detect_policy_violations(answer_text, question, evaluation, historical_answer_index):
    result = empty_policy_result()
    cleaned_answer = (answer_text or "").strip()
    if not cleaned_answer:
        return result

    normalized_answer = _normalize_similarity_text(cleaned_answer)
    answer_tokens = [token for token in normalized_answer.split() if token]
    if not answer_tokens:
        return result

    lowered_answer = cleaned_answer.lower()

    direct_ai_hits = _find_direct_ai_hits(lowered_answer, normalized_answer)
    style_ai_hits = _find_style_ai_hits(lowered_answer, normalized_answer)

    nlp_model = get_nlp_model()
    doc = nlp_model(cleaned_answer)
    (
        ai_risk,
        ai_flag,
        ai_signal_count,
        ai_strong_signal_count,
        ai_decision_rule,
        ai_signal_breakdown,
    ) = compute_ai_risk_signals(
        cleaned_answer=cleaned_answer,
        answer_tokens=answer_tokens,
        doc=doc,
        evaluation=evaluation,
        direct_ai_hits=direct_ai_hits,
        style_ai_hits=style_ai_hits,
    )

    reference_answer = str(question.get("reference_answer", "") or "")
    normalized_reference = _normalize_similarity_text(reference_answer)
    reference_similarity = _sequence_similarity(normalized_answer, normalized_reference)

    question_key = _question_key_from_text(get_display_question_text(question))
    historical_answers = historical_answer_index.get(question_key, []) if historical_answer_index else []

    max_historical_similarity = 0.0
    exact_duplicate = False

    for historical_answer in historical_answers:
        normalized_historical = _normalize_similarity_text(historical_answer)
        if not normalized_historical:
            continue

        similarity = _sequence_similarity(normalized_answer, normalized_historical)
        max_historical_similarity = max(max_historical_similarity, similarity)

        if normalized_historical == normalized_answer and len(normalized_answer.split()) >= 8:
            exact_duplicate = True

    plagiarism_score = round(max(reference_similarity, max_historical_similarity) * 100, 1)

    plagiarism_flag = bool(exact_duplicate)

    violation_flags = []
    if ai_flag:
        violation_flags.append("AI-generated answer suspected")
    if plagiarism_flag:
        violation_flags.append("Plagiarism suspected")

    result.update(
        {
            "ai_risk_score": ai_risk,
            "plagiarism_score": plagiarism_score,
            "ai_flag": ai_flag,
            "plagiarism_flag": plagiarism_flag,
            "ai_signal_count": int(ai_signal_count),
            "ai_strong_signal_count": int(ai_strong_signal_count),
            "ai_decision_rule": ai_decision_rule,
            "ai_signal_breakdown": ai_signal_breakdown,
            "violation_flags": violation_flags,
            "violation_remark": "; ".join(violation_flags),
        }
    )
    return result

def get_active_ban(username):
    cursor.execute(
        """
        SELECT id, COALESCE(is_banned, 0), ban_until, ban_reason
        FROM candidate_profiles
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (username,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    profile_id, is_banned, ban_until_raw, ban_reason = row
    if not is_banned:
        return None

    today = datetime.date.today()
    ban_until_date = None

    if ban_until_raw:
        try:
            ban_until_date = datetime.date.fromisoformat(str(ban_until_raw))
        except ValueError:
            ban_until_date = today + datetime.timedelta(days=365)
    else:
        ban_until_date = today + datetime.timedelta(days=365)

    if ban_until_date < today:
        cursor.execute(
            """
            UPDATE candidate_profiles
            SET is_banned = 0,
                ban_until = NULL,
                ban_reason = NULL
            WHERE id = ?
            """,
            (profile_id,),
        )
        conn.commit()
        return None

    return {
        "ban_until": ban_until_date.isoformat(),
        "ban_reason": str(ban_reason or "Policy violation detected during interview.").strip(),
    }
def save_interview_results(username, role, experience, results, original_answers):
    """Save interview results into DB."""
    cursor.execute(
        """
        INSERT INTO interview_results (
            username, role, experience,
            correct_normal, partial_normal, incorrect_normal,
            correct_hard, partial_hard, incorrect_hard, original_answers, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            username,
            role,
            experience,
            results["correct_normal"],
            results["partial_normal"],
            results["incorrect_normal"],
            results["correct_hard"],
            results["partial_hard"],
            results["incorrect_hard"],
            original_answers,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def get_latest_interview_result(username):
    cursor.execute(
        """
        SELECT correct_normal, partial_normal, correct_hard, partial_hard
        FROM interview_results
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (username,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "correct_normal": row[0],
        "partial_normal": row[1],
        "correct_hard": row[2],
        "partial_hard": row[3],
    }


def get_display_score(results):
    return results["correct_normal"] + results["partial_normal"] + results["correct_hard"] + results["partial_hard"]


def build_original_answers_payload(username, questions, historical_answer_index):
    payload = []
    for question_index, question in enumerate(questions):
        answer_text = st.session_state.answer_drafts.get(question_index, "").strip()
        evaluation = empty_evaluation_result()
        policy = empty_policy_result()
        audio_payload = st.session_state.answer_audio_blobs.get(question_index, {})
        audio_base64 = audio_payload.get("audio_base64", "") if isinstance(audio_payload, dict) else ""
        audio_mime = audio_payload.get("audio_mime", "audio/wav") if isinstance(audio_payload, dict) else "audio/wav"

        if answer_text:
            evaluation = evaluate_answer(
                answer_text,
                question.get("keywords", []),
                question.get("reference_answer", ""),
            )
            policy = detect_policy_violations(answer_text, question, evaluation, historical_answer_index)

        payload.append(
            {
                "question_no": question_index + 1,
                "question_text": get_display_question_text(question),
                "answer_text": answer_text,
                "result_label": evaluation["result_label"],
                "difficulty": question["difficulty"],
                "topic": infer_topic(question),
                "relevance_score": evaluation["relevance_score"],
                "confidence_score": evaluation["confidence_score"],
                "matched_keywords": evaluation["matched_keywords"],
                "missing_keywords": evaluation["missing_keywords"],
                "scoring_breakdown": {
                    "coverage": evaluation["coverage_score"],
                    "semantic_similarity": evaluation["semantic_similarity_score"],
                    "length_quality": evaluation["length_quality_score"],
                    "signal_agreement": evaluation["signal_agreement_score"],
                    "boundary_margin": evaluation["boundary_margin_score"],
                    "evidence_strength": evaluation["evidence_strength_score"],
                },
                "improvement_insights": evaluation["improvement_insights"],
                "ai_risk_score": policy["ai_risk_score"],
                "plagiarism_score": policy["plagiarism_score"],
                "ai_flag": policy["ai_flag"],
                "plagiarism_flag": policy["plagiarism_flag"],
                "ai_signal_count": policy.get("ai_signal_count", 0),
                "ai_strong_signal_count": policy.get("ai_strong_signal_count", 0),
                "ai_decision_rule": policy.get("ai_decision_rule", ""),
                "ai_signal_breakdown": policy.get("ai_signal_breakdown", {}),
                "violation_flags": policy["violation_flags"],
                "violation_remark": policy["violation_remark"],
                "audio_base64": audio_base64,
                "audio_mime": audio_mime,
            }
        )
    return payload

def compile_results(username, questions, historical_answer_index):
    results = {
        "correct_normal": 0,
        "partial_normal": 0,
        "incorrect_normal": 0,
        "correct_hard": 0,
        "partial_hard": 0,
        "incorrect_hard": 0,
    }

    for question_index, question in enumerate(questions):
        answer_text = st.session_state.answer_drafts.get(question_index, "").strip()
        difficulty = question["difficulty"].lower()
        evaluation = empty_evaluation_result()
        policy = empty_policy_result()
        result = evaluation["result_label"]

        if answer_text:
            evaluation = evaluate_answer(
                answer_text,
                question.get("keywords", []),
                question.get("reference_answer", ""),
            )
            policy = detect_policy_violations(answer_text, question, evaluation, historical_answer_index)
            result = evaluation["result_label"]
            display_question_text = get_display_question_text(question)

            st.session_state.answers[display_question_text] = {
                "answer": answer_text,
                "result": result,
                "difficulty": question["difficulty"],
                "relevance_score": evaluation["relevance_score"],
                "confidence_score": evaluation["confidence_score"],
                "matched_keywords": evaluation["matched_keywords"],
                "missing_keywords": evaluation["missing_keywords"],
                "scoring_breakdown": {
                    "coverage": evaluation["coverage_score"],
                    "semantic_similarity": evaluation["semantic_similarity_score"],
                    "length_quality": evaluation["length_quality_score"],
                    "signal_agreement": evaluation["signal_agreement_score"],
                    "boundary_margin": evaluation["boundary_margin_score"],
                    "evidence_strength": evaluation["evidence_strength_score"],
                },
                "improvement_insights": evaluation["improvement_insights"],
                "ai_risk_score": policy["ai_risk_score"],
                "plagiarism_score": policy["plagiarism_score"],
                "ai_flag": policy["ai_flag"],
                "plagiarism_flag": policy["plagiarism_flag"],
                "ai_signal_count": policy.get("ai_signal_count", 0),
                "ai_strong_signal_count": policy.get("ai_strong_signal_count", 0),
                "ai_decision_rule": policy.get("ai_decision_rule", ""),
                "ai_signal_breakdown": policy.get("ai_signal_breakdown", {}),
                "violation_flags": policy["violation_flags"],
                "violation_remark": policy["violation_remark"],
            }
        else:
            st.session_state.answers.pop(get_display_question_text(question), None)

        is_hard = difficulty == "hard"
        if result == "Correct":
            if is_hard:
                results["correct_hard"] += 1
            else:
                results["correct_normal"] += 1
        elif result == "Partially Correct":
            if is_hard:
                results["partial_hard"] += 1
            else:
                results["partial_normal"] += 1
        else:
            if is_hard:
                results["incorrect_hard"] += 1
            else:
                results["incorrect_normal"] += 1

    return results


def show_page_navigation(total_questions, current_index, answer_widget_key):
    st.markdown("### Questions")
    options = [index + 1 for index in range(total_questions)]

    selected_page = None
    if hasattr(st, "segmented_control"):
        selected_page = st.segmented_control(
            "Question Navigation",
            options=options,
            default=options[current_index],
            label_visibility="collapsed",
        )
    else:
        nav_cols = st.columns(total_questions)
        selected_page = current_index + 1
        for option_index, nav_col in enumerate(nav_cols):
            page_no = option_index + 1
            is_current = option_index == current_index
            with nav_col:
                button_type = "primary" if is_current else "secondary"
                if st.button(str(page_no), key=f"page_btn_{page_no}", type=button_type, width="content"):
                    selected_page = page_no

    if selected_page is not None:
        target_index = int(selected_page) - 1
        if target_index != current_index:
            st.session_state.answer_drafts[current_index] = st.session_state.get(answer_widget_key, "")
            st.session_state.current_index = target_index
            st.rerun()


def submit_interview_now(username, role, experience, questions):
    historical_answer_index = build_historical_answer_index(username)
    results = compile_results(username, questions, historical_answer_index)
    answer_payload = build_original_answers_payload(username, questions, historical_answer_index)
    st.session_state.results_summary = results

    if not st.session_state.results_saved:
        original_answers = json.dumps(answer_payload)
        save_interview_results(username, role, experience, results, original_answers)
        st.session_state.results_saved = True

    st.session_state.interview_submitted = True
    st.session_state.allow_retest = False
    st.session_state.show_answer_review = False


def render_review_answers_panel(total_questions, _current_index):
    answered_count = 0
    review_rows = []
    for question_index in range(total_questions):
        answer_text = st.session_state.answer_drafts.get(question_index, "").strip()
        if answer_text:
            answered_count += 1
            preview = answer_text if len(answer_text) <= 90 else f"{answer_text[:90]}..."
            status = "Answered"
        else:
            preview = "-"
            status = "Pending"
        review_rows.append(
            {
                "Question": question_index + 1,
                "Status": status,
                "Answer Preview": preview,
            }
        )

    with st.container(border=True):
        st.markdown(f"#### Review Answers ({answered_count}/{total_questions} answered)")
        review_df = pd.DataFrame(review_rows)
        review_df.index = review_df.index + 1
        st.dataframe(review_df, width="stretch")


# --- Interview runner ---
def run_interview(username, role, experience):
    st.markdown(
        """
<div class="brand-bar">
  <div class="brand-logo"><span class="brand-main">ABC</span><span class="brand-inc">INC</span></div>
  <div>
    <div class="brand-title">ABC INC Interview</div>
    <div class="brand-subtitle">Structured Interview Session</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.markdown(
        """
<div class="sticky-quick-links">
  <a href="#interview-summary">Candidate Info</a>
  <a href="#current-question">Question</a>
  <a href="#question-nav">Navigation</a>
  <a href="#submission">Submit</a>
</div>
""",
        unsafe_allow_html=True,
    )
    st.title("Candidate Interview")

    ban_status = get_active_ban(username)
    if ban_status:
        st.warning("Interview access is currently unavailable. Please contact support.")
        if st.button("Go to Home Page"):
            st.session_state.allow_retest = False
            st.session_state.show_answer_review = False
            save_browser_session(conn)
            switch_page("login.py")
        return

    allow_retest = bool(st.session_state.get("allow_retest", False))
    existing_result = get_latest_interview_result(username)
    if existing_result and not allow_retest:
        score = get_display_score(existing_result)
        st.success("Interview already completed.")
        st.info(f"Your score: {score} / 15")
        if st.button("Go to Home Page"):
            st.session_state.show_answer_review = False
            save_browser_session(conn)
            switch_page("login.py")
        return
    if existing_result and allow_retest:
        st.info("Retest mode is active. Your new submission will be saved as a new interview attempt.")

    requested_total_questions = 15
    selected_primary_skill = st.session_state.get("selected_primary_skill", "")
    selected_specializations = st.session_state.get("selected_specializations", [])
    question_meta = {
        "role": role,
        "experience": experience,
        "selected_primary_skill": _normalize_text(selected_primary_skill),
        "selected_specializations": tuple(sorted(_normalize_list(selected_specializations))),
        "total_questions": int(requested_total_questions),
    }
    if st.session_state.get("interview_questions_meta") != question_meta:
        st.session_state.interview_questions_meta = question_meta
        st.session_state.interview_questions = get_questions(
            role,
            experience,
            selected_primary_skill,
            selected_specializations,
            total_questions=requested_total_questions,
        )

    questions = st.session_state.get("interview_questions", [])
    if not questions:
        st.error("No questions found for this role and experience combination.")
        return

    total_questions = len(questions)
    if total_questions < requested_total_questions:
        st.warning(
            f"Only {total_questions} questions were found for your selected specializations. "
            "The interview will continue with the available questions."
        )

    if selected_primary_skill:
        specialization_text = ", ".join(selected_specializations) if selected_specializations else "Not specified"
        st.caption(f"Interview Focus: {selected_primary_skill} | Specializations: {specialization_text}")

    if st.session_state.interview_submitted and st.session_state.results_summary:
        st.markdown(
            """
<div class="status-box"><div class="status-message">Our Team will contact you soon</div></div>
""",
            unsafe_allow_html=True,
        )
        return

    _, deadline_epoch = _ensure_interview_timer()
    remaining_seconds = _get_remaining_interview_seconds(deadline_epoch)
    if remaining_seconds <= 0:
        _sync_answer_drafts_from_widget_state()
        submit_interview_now(username, role, experience, questions)
        save_browser_session(conn)
        st.rerun()

    render_interview_timer(deadline_epoch)

    idx = max(0, min(st.session_state.current_index, total_questions - 1))
    st.session_state.current_index = idx
    question = questions[idx]
    display_question_text = get_display_question_text(question)

    progress_text = f"{idx + 1} / {total_questions}"
    st.markdown(
        f"""
<a id="interview-summary"></a>
<div class="summary-card">
  <div style="font-size:20px;font-weight:700;">Interview Snapshot</div>
  <div class="summary-grid">
    <div class="summary-item"><div class="summary-label">Candidate</div><div class="summary-value">{display_name}</div></div>
    <div class="summary-item"><div class="summary-label">Role</div><div class="summary-value">{role}</div></div>
    <div class="summary-item"><div class="summary-label">Experience</div><div class="summary-value">{experience}</div></div>
    <div class="summary-item"><div class="summary-label">Progress</div><div class="summary-value">{progress_text}</div></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown('<a id="current-question"></a>', unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader(f"Question {idx + 1} of {total_questions}")
        st.write(display_question_text)

        answer_mode = st.radio(
            "Answer Mode",
            ["Speech", "Text"],
            key="answer_mode",
            horizontal=True,
        )
        st.caption("You can switch to Text mode anytime if microphone capture does not work.")

        inject_answer_security_guards()
        st.caption(
            "Interview security mode is active: copy, paste, cut, right-click, and tab/app switching are monitored."
        )

        question_id = f"{idx}:{display_question_text}"
        if answer_mode == "Speech":
            speak_question_text(question_id, display_question_text)
            if st.button("Speak Question Again", key=f"speak_again_{idx}"):
                speak_question_text(question_id, display_question_text, force=True)

        answer_widget_key = f"ans_{idx}"
        if answer_widget_key not in st.session_state:
            st.session_state[answer_widget_key] = st.session_state.answer_drafts.get(idx, "")

        if answer_mode == "Speech":
            st.caption("Press Record, speak your answer, then press Done to stop recording.")

            if hasattr(st, "audio_input"):
                audio_widget_key = f"recorded_audio_{idx}"
                recorded_audio = st.audio_input("Record Answer", key=audio_widget_key)

                if recorded_audio is not None:
                    try:
                        transcript, audio_digest = transcribe_uploaded_audio(recorded_audio)
                        digest_key = f"processed_audio_digest_{idx}"
                        if audio_digest and st.session_state.get(digest_key) != audio_digest:
                            st.session_state[digest_key] = audio_digest
                            audio_bytes = recorded_audio.getvalue()
                            audio_mime = getattr(recorded_audio, "type", None) or "audio/wav"
                            st.session_state.answer_audio_blobs[idx] = {
                                "audio_base64": encode_audio_blob(audio_bytes),
                                "audio_mime": audio_mime,
                            }
                            transcript = transcript.strip()
                            if transcript:
                                st.session_state[answer_widget_key] = transcript
                                st.session_state.answer_drafts[idx] = transcript
                                st.success("Answer recorded successfully. You can go to the next question.")
                            else:
                                st.warning("No speech content recognized. Please record again.")
                    except sr.UnknownValueError:
                        st.warning("Sorry, audio not recognizable. Please record again.")
                    except sr.RequestError:
                        st.error("Speech recognition service is not reachable. Switch to Text mode or try later.")
                    except Exception as exc:
                        st.error(f"Voice transcription failed: {exc}")
            else:
                st.info("Done-button recording is unavailable in this Streamlit version. Falling back to microphone capture.")
                if st.button("Record Answer via Microphone", key=f"record_answer_{idx}"):
                    try:
                        transcript = listen_for_answer(timeout=None, phrase_time_limit=None, ambient_duration=2)
                        transcript = transcript.strip()
                        if transcript:
                            st.session_state[answer_widget_key] = transcript
                            st.session_state.answer_drafts[idx] = transcript
                            st.success("Voice captured successfully. You can go to the next question.")
                        else:
                            st.warning("No speech content recognized. Please try again.")
                    except sr.UnknownValueError:
                        st.warning("Sorry, audio not recognizable. Please try again.")
                    except sr.RequestError:
                        st.error("Speech recognition service is not reachable. Switch to Text mode or try later.")
                    except OSError:
                        st.error("Microphone not accessible on this machine. Switch to Text mode.")
                    except Exception as exc:
                        st.error(f"Voice capture failed: {exc}")

        stored_audio_payload = st.session_state.answer_audio_blobs.get(idx, {})
        if isinstance(stored_audio_payload, dict):
            stored_audio_b64 = stored_audio_payload.get("audio_base64", "")
            stored_audio_mime = stored_audio_payload.get("audio_mime", "audio/wav")
            stored_audio_bytes = decode_audio_blob(stored_audio_b64)
            if stored_audio_bytes:
                st.caption("Recorded audio preview:")
                st.audio(stored_audio_bytes, format=stored_audio_mime)

        answer_label = "Recognized Answer (You can edit)" if answer_mode == "Speech" else "Your Answer"
        answer = st.text_area(answer_label, key=answer_widget_key, height=180)
        st.session_state.answer_drafts[idx] = answer

    st.markdown('<a id="submission"></a>', unsafe_allow_html=True)
    col_prev, col_next, col_review, col_submit = st.columns([1, 1, 1, 1.15])
    with col_prev:
        if st.button("Previous", disabled=idx == 0):
            st.session_state.answer_drafts[idx] = st.session_state.get(answer_widget_key, "")
            st.session_state.current_index = idx - 1
            st.rerun()

    with col_next:
        if st.button("Next", disabled=idx >= total_questions - 1):
            st.session_state.answer_drafts[idx] = st.session_state.get(answer_widget_key, "")
            st.session_state.current_index = idx + 1
            st.rerun()

    with col_review:
        if st.button("Review Answers", key=f"toggle_review_{idx}", width="stretch"):
            st.session_state.show_answer_review = not st.session_state.get("show_answer_review", False)

    with col_submit:
        if st.button("Submit Interview", key=f"submit_interview_{idx}", type="primary", width="stretch"):
            st.session_state.answer_drafts[idx] = st.session_state.get(answer_widget_key, "")
            submit_interview_now(username, role, experience, questions)
            st.rerun()

    if st.session_state.get("show_answer_review", False):
        render_review_answers_panel(total_questions, idx)

    st.markdown('<a id="question-nav"></a>', unsafe_allow_html=True)
    show_page_navigation(total_questions, idx, answer_widget_key)
run_interview(username, role, experience)
save_browser_session(conn)
