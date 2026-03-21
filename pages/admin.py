import json
import sqlite3
import datetime
import base64
import html
import textwrap
from pathlib import Path
import pandas as pd
import streamlit as st
from browser_session import clear_browser_session, restore_browser_session, save_browser_session, switch_page

conn = sqlite3.connect("users.db", check_same_thread=False)

ADMIN_AI_BAN_REASON = "Manual admin ban after AI-risk review."
ADMIN_PLAGIARISM_BAN_REASON = "Manual admin ban after plagiarism-risk review."


def ensure_schema():
    profile_columns = {row[1] for row in conn.execute("PRAGMA table_info(candidate_profiles)").fetchall()}
    result_columns = {row[1] for row in conn.execute("PRAGMA table_info(interview_results)").fetchall()}

    if "is_banned" not in profile_columns:
        conn.execute("ALTER TABLE candidate_profiles ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0")
    if "display_name" not in profile_columns:
        conn.execute("ALTER TABLE candidate_profiles ADD COLUMN display_name TEXT")
    if "interview_auth_status" not in profile_columns:
        conn.execute("ALTER TABLE candidate_profiles ADD COLUMN interview_auth_status TEXT")
    if "interview_auth_updated_at" not in profile_columns:
        conn.execute("ALTER TABLE candidate_profiles ADD COLUMN interview_auth_updated_at TEXT")
    if "ban_until" not in profile_columns:
        conn.execute("ALTER TABLE candidate_profiles ADD COLUMN ban_until TEXT")
    if "ban_reason" not in profile_columns:
        conn.execute("ALTER TABLE candidate_profiles ADD COLUMN ban_reason TEXT")
    if "created_at" not in profile_columns:
        conn.execute("ALTER TABLE candidate_profiles ADD COLUMN created_at TEXT")
    if "created_at" not in result_columns:
        conn.execute("ALTER TABLE interview_results ADD COLUMN created_at TEXT")

    conn.execute(
        "UPDATE candidate_profiles SET display_name = COALESCE(NULLIF(display_name, ''), username) "
        "WHERE display_name IS NULL OR display_name = ''"
    )
    conn.execute("UPDATE candidate_profiles SET created_at = datetime('now') WHERE created_at IS NULL OR created_at = ''")
    conn.execute("UPDATE interview_results SET created_at = datetime('now') WHERE created_at IS NULL OR created_at = ''")

    conn.execute(
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


ensure_schema()


def get_dashboard_data():
    query = """
    SELECT cp.username,
           COALESCE(cp.display_name, cp.username) AS display_name,
           cp.email,
           cp.phone,
           cp.experience,
           cp.previous_role,
           cp.role AS applied_role,
           cp.interview_auth_status,
           cp.interview_auth_updated_at,
           cp.skills,
           COALESCE(cp.is_banned, 0) AS is_banned,
           cp.ban_until,
           cp.ban_reason,
           cp.created_at AS profile_created_at,
           ir.correct_normal, ir.partial_normal, ir.incorrect_normal,
           ir.correct_hard, ir.partial_hard, ir.incorrect_hard,
           ir.created_at AS interview_created_at,
           (
               COALESCE(ir.correct_normal, 0) +
               COALESCE(ir.partial_normal, 0) +
               COALESCE(ir.correct_hard, 0) +
               COALESCE(ir.partial_hard, 0)
           ) AS total_score
    FROM candidate_profiles cp
    LEFT JOIN interview_results ir
        ON ir.id = (
            SELECT id
            FROM interview_results
            WHERE username = cp.username
            ORDER BY id DESC
            LIMIT 1
        )
    WHERE cp.id = (
        SELECT id
        FROM candidate_profiles
        WHERE username = cp.username
        ORDER BY id DESC
        LIMIT 1
    )
    ORDER BY cp.id DESC
    """
    df = pd.read_sql_query(query, conn)
    if not df.empty:
        df["total_score"] = df["total_score"].fillna(0).astype(int)
        df["total_score_out_of_15"] = df["total_score"].astype(str) + "/15"
        df["display_name"] = df["display_name"].fillna("").astype(str).str.strip()
        df.loc[df["display_name"] == "", "display_name"] = df["username"].astype(str)
        df["interview_auth_status"] = df["interview_auth_status"].fillna("").astype(str)

        today = datetime.date.today()
        ban_status = []
        for _, row in df.iterrows():
            is_banned = bool(int(row.get("is_banned", 0) or 0))
            ban_until_raw = row.get("ban_until")
            if not is_banned:
                ban_status.append("Active")
                continue

            ban_until_text = ""
            if isinstance(ban_until_raw, str) and ban_until_raw.strip():
                try:
                    parsed_ban_date = datetime.date.fromisoformat(ban_until_raw.strip())
                    if parsed_ban_date < today:
                        ban_status.append("Active")
                        continue
                    ban_until_text = parsed_ban_date.isoformat()
                except ValueError:
                    ban_until_text = ban_until_raw.strip()
            else:
                ban_until_text = "Unknown"

            ban_status.append(f"Banned until {ban_until_text}")

        df["ban_status"] = ban_status
    return df


def _format_attempt_timestamp(raw_value):
    raw_text = str(raw_value or "").strip()
    if not raw_text:
        return "Unknown date"
    try:
        parsed = datetime.datetime.fromisoformat(raw_text.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return raw_text


def get_candidate_interview_attempts(username):
    rows = conn.execute(
        """
        SELECT
            id,
            role,
            experience,
            COALESCE(correct_normal, 0) +
            COALESCE(partial_normal, 0) +
            COALESCE(correct_hard, 0) +
            COALESCE(partial_hard, 0) AS total_score,
            created_at
        FROM interview_results
        WHERE username = ?
        ORDER BY id DESC
        """,
        (username,),
    ).fetchall()

    attempts = []
    total_attempts = len(rows)
    for index, row in enumerate(rows):
        interview_id = int(_safe_float(row[0], 0.0))
        role_name = str(row[1] or "").strip() or "Unknown"
        experience_value = str(row[2] or "").strip() or "Unknown"
        score = int(_safe_float(row[3], 0.0))
        created_at = row[4]
        sequence_no = total_attempts - index
        timestamp_label = _format_attempt_timestamp(created_at)
        attempts.append(
            {
                "id": interview_id,
                "role": role_name,
                "experience": experience_value,
                "score": score,
                "created_at": created_at,
                "sequence_no": sequence_no,
                "timestamp_label": timestamp_label,
                "label": f"Attempt {sequence_no} | {timestamp_label} | {role_name} | Score {score}/15",
            }
        )
    return attempts


def get_original_answers(username, interview_id=None):
    if interview_id is None:
        query = """
        SELECT original_answers
        FROM interview_results
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 1
        """
        params = (username,)
    else:
        query = """
        SELECT original_answers
        FROM interview_results
        WHERE username = ? AND id = ?
        LIMIT 1
        """
        params = (username, int(interview_id))

    row = conn.execute(query, params).fetchone()
    if not row or not row[0]:
        return []
    try:
        parsed = json.loads(row[0])
        if not isinstance(parsed, list):
            return []
        return [item for item in parsed if isinstance(item, dict)]
    except (json.JSONDecodeError, TypeError):
        return []


def get_interview_result_snapshot(username, interview_id=None):
    if interview_id is None:
        query = """
        SELECT
            id,
            role,
            COALESCE(correct_normal, 0) +
            COALESCE(partial_normal, 0) +
            COALESCE(correct_hard, 0) +
            COALESCE(partial_hard, 0) AS total_score,
            created_at
        FROM interview_results
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 1
        """
        params = (username,)
    else:
        query = """
        SELECT
            id,
            role,
            COALESCE(correct_normal, 0) +
            COALESCE(partial_normal, 0) +
            COALESCE(correct_hard, 0) +
            COALESCE(partial_hard, 0) AS total_score,
            created_at
        FROM interview_results
        WHERE username = ? AND id = ?
        LIMIT 1
        """
        params = (username, int(interview_id))

    row = conn.execute(query, params).fetchone()
    if not row:
        return None
    return {
        "id": int(_safe_float(row[0], 0.0)),
        "role": str(row[1] or "").strip(),
        "score": int(_safe_float(row[2], 0.0)),
        "created_at": row[3],
    }


def get_latest_candidate_role(username):
    row = conn.execute(
        """
        SELECT role
        FROM candidate_profiles
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (username,),
    ).fetchone()
    if not row:
        return ""
    return str(row[0] or "").strip()


def get_latest_candidate_profile_snapshot(username):
    row = conn.execute(
        """
        SELECT display_name, phone, email, experience, previous_role
        FROM candidate_profiles
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (username,),
    ).fetchone()
    if not row:
        return {
            "display_name": "Not provided",
            "phone": "Not provided",
            "email": "Not provided",
            "experience": "Not provided",
            "previous_role": "Not provided",
        }
    return {
        "display_name": str(row[0] or "Not provided").strip() or "Not provided",
        "phone": str(row[1] or "Not provided").strip() or "Not provided",
        "email": str(row[2] or "Not provided").strip() or "Not provided",
        "experience": str(row[3] or "Not provided").strip() or "Not provided",
        "previous_role": str(row[4] or "Not provided").strip() or "Not provided",
    }


def get_latest_interview_score(username, interview_id=None):
    snapshot = get_interview_result_snapshot(username, interview_id=interview_id)
    if not snapshot:
        return "Pending"
    return f"{int(_safe_float(snapshot['score'], 0.0))} / 15"


def build_role_performance_suggestion(avg_score, avg_relevance, avg_confidence, improvement_hint):
    if avg_score >= 11 and avg_relevance >= 75 and avg_confidence >= 65:
        base = "Strong consistency. Ready for advanced, production-grade evaluation."
    elif avg_score >= 8:
        base = "Good progress. Improve depth and structure for stronger role readiness."
    else:
        base = "Needs stronger fundamentals with clearer concepts and practical examples."

    hint = str(improvement_hint or "").strip()
    if hint:
        return f"{base} Priority: {hint}"
    return base


def get_candidate_multi_interview_insights(username):
    rows = conn.execute(
        """
        SELECT role, correct_normal, partial_normal, correct_hard, partial_hard, original_answers
        FROM interview_results
        WHERE username = ?
        ORDER BY id DESC
        """,
        (username,),
    ).fetchall()

    if not rows:
        return {
            "total_attempts": 0,
            "role_insights": [],
            "all_roles_covered": False,
            "attempted_roles": [],
        }

    role_aggregate = {}
    for row in rows:
        role_name = str(row[0] or "Unknown").strip() or "Unknown"
        interview_score = int(_safe_float(row[1], 0.0) + _safe_float(row[2], 0.0) + _safe_float(row[3], 0.0) + _safe_float(row[4], 0.0))
        answer_rows = []
        raw_answers = row[5]
        if raw_answers:
            try:
                parsed_answers = json.loads(raw_answers)
                if isinstance(parsed_answers, list):
                    answer_rows = [item for item in parsed_answers if isinstance(item, dict)]
            except (TypeError, json.JSONDecodeError):
                answer_rows = []

        bucket = role_aggregate.setdefault(
            role_name,
            {"attempts": 0, "score_total": 0.0, "answer_rows": []},
        )
        bucket["attempts"] += 1
        bucket["score_total"] += interview_score
        bucket["answer_rows"].extend(answer_rows)

    ordered_roles = ["Developer", "Tester", "Analyst"]
    sort_index = {name: index for index, name in enumerate(ordered_roles)}
    attempted_roles = sorted(role_aggregate.keys(), key=lambda name: sort_index.get(name, 999))
    role_insights = []

    for role_name in attempted_roles:
        bucket = role_aggregate[role_name]
        attempts = int(bucket["attempts"])
        avg_score = (bucket["score_total"] / attempts) if attempts else 0.0
        feedback = build_feedback_summary(bucket["answer_rows"]) if bucket["answer_rows"] else None
        avg_relevance = _safe_float(feedback.get("avg_relevance"), 0.0) if feedback else 0.0
        avg_confidence = _safe_float(feedback.get("avg_confidence"), 0.0) if feedback else 0.0
        improvement_hint = ""
        if feedback:
            improvements = feedback.get("improvements", [])
            if isinstance(improvements, list) and improvements:
                improvement_hint = str(improvements[0] or "").strip()

        role_insights.append(
            {
                "Role": role_name,
                "Attempts": attempts,
                "Average Score (/15)": round(avg_score, 2),
                "Avg Relevance (%)": round(avg_relevance, 1),
                "Avg Confidence (%)": round(avg_confidence, 1),
                "Suggestion": build_role_performance_suggestion(
                    avg_score,
                    avg_relevance,
                    avg_confidence,
                    improvement_hint,
                ),
            }
        )

    required_roles = {"Developer", "Tester", "Analyst"}
    all_roles_covered = required_roles.issubset(set(attempted_roles))

    return {
        "total_attempts": len(rows),
        "role_insights": role_insights,
        "all_roles_covered": all_roles_covered,
        "attempted_roles": attempted_roles,
    }


def _is_review_resolved_action(action_name):
    resolved_actions = {
        "SCHEDULE_NEXT_ROUND",
        "SEND_FEEDBACK",
        "BAN",
        "UNBAN",
    }
    return str(action_name or "").strip().upper() in resolved_actions


def get_latest_admin_action_map(usernames):
    normalized_users = [str(user).strip() for user in usernames if str(user).strip()]
    if not normalized_users:
        return {}

    placeholders = ",".join(["?"] * len(normalized_users))
    rows = conn.execute(
        f"""
        SELECT username, action
        FROM admin_audit_log
        WHERE username IN ({placeholders})
        ORDER BY id DESC
        """,
        tuple(normalized_users),
    ).fetchall()

    latest_actions = {}
    for row in rows:
        username = str(row[0] or "").strip()
        action = str(row[1] or "").strip()
        if username and username not in latest_actions:
            latest_actions[username] = action
    return latest_actions


def get_active_ban_status(username):
    row = conn.execute(
        """
        SELECT COALESCE(is_banned, 0), ban_until, ban_reason
        FROM candidate_profiles
        WHERE username = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (username,),
    ).fetchone()
    if not row:
        return None

    is_banned, ban_until_raw, ban_reason = row
    if not bool(int(is_banned or 0)):
        return None

    today = datetime.date.today()
    ban_until_date = None

    if isinstance(ban_until_raw, str) and ban_until_raw.strip():
        try:
            ban_until_date = datetime.date.fromisoformat(ban_until_raw.strip())
        except ValueError:
            ban_until_date = None

    if ban_until_date and ban_until_date < today:
        return None

    ban_until_text = ban_until_date.isoformat() if ban_until_date else (str(ban_until_raw or "Unknown").strip())
    return {
        "ban_until": ban_until_text,
        "ban_reason": str(ban_reason or "Policy violation detected during interview.").strip(),
    }


def log_admin_action(username, action, reason="", actor="Admin"):
    conn.execute(
        """
        INSERT INTO admin_audit_log (username, action, reason, actor, created_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        """,
        (username, action, reason, actor),
    )
    conn.commit()


def get_audit_trail(limit=120):
    query = """
    SELECT username, action, reason, actor, created_at
    FROM admin_audit_log
    ORDER BY id DESC
    LIMIT ?
    """
    return pd.read_sql_query(query, conn, params=(int(limit),))


def ban_candidate_from_admin(username, reason, actor="Admin"):
    ban_until = (datetime.date.today() + datetime.timedelta(days=365)).isoformat()
    conn.execute(
        """
        UPDATE candidate_profiles
        SET is_banned = 1,
            ban_until = ?,
            ban_reason = ?
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
    log_admin_action(username, "BAN", reason, actor)
    return {
        "ban_until": ban_until,
        "ban_reason": reason,
    }


def unban_candidate_from_admin(username, actor="Admin"):
    conn.execute(
        """
        UPDATE candidate_profiles
        SET is_banned = 0,
            ban_until = NULL,
            ban_reason = NULL
        WHERE id = (
            SELECT id
            FROM candidate_profiles
            WHERE username = ?
            ORDER BY id DESC
            LIMIT 1
        )
        """,
        (username,),
    )
    conn.commit()
    log_admin_action(username, "UNBAN", "Manual unban after admin review.", actor)


def set_interview_auth_status(username, status, actor="Admin"):
    conn.execute(
        """
        UPDATE candidate_profiles
        SET interview_auth_status = ?, interview_auth_updated_at = datetime('now')
        WHERE id = (
            SELECT id
            FROM candidate_profiles
            WHERE username = ?
            ORDER BY id DESC
            LIMIT 1
        )
        """,
        (status, username),
    )
    conn.commit()
    log_admin_action(username, f"INTERVIEW_AUTH_{status.upper()}", f"Interview access {status}.", actor)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _format_chart_label(value):
    numeric = _safe_float(value, 0.0)
    if pd.isna(numeric):
        numeric = 0.0
    return f"{numeric:.1f}" if abs(numeric - round(numeric)) > 0.01 else f"{int(round(numeric))}"


def _split_skill_payload(skills_text):
    items = [item.strip() for item in str(skills_text or "").split(",") if item.strip()]
    primary = ""
    specs = []
    for item in items:
        if " - " in item:
            main, spec = item.split(" - ", 1)
            main = main.strip()
            spec = spec.strip()
            if main and not primary:
                primary = main
            if spec and spec not in specs:
                specs.append(spec)
        else:
            if not primary:
                primary = item
    return primary, ", ".join(specs)


def decode_audio_blob(audio_base64):
    if not audio_base64:
        return b""
    try:
        return base64.b64decode(audio_base64)
    except (TypeError, ValueError):
        return b""


def _escape_html(value):
    return html.escape(str(value or ""), quote=True)


def _parse_date(value):
    text_value = str(value or "").strip()
    if not text_value:
        return None
    for candidate in [text_value, text_value[:10]]:
        try:
            return datetime.date.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def _file_data_uri(image_path):
    try:
        path_obj = Path(str(image_path))
        if not path_obj.exists() or not path_obj.is_file():
            return ""
        suffix = path_obj.suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        mime = mime_map.get(suffix, "image/jpeg")
        payload = base64.b64encode(path_obj.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{payload}"
    except OSError:
        return ""


def _pdf_escape_text(value):
    return str(value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(title, lines):
    wrapped_lines = []
    wrapped_lines.extend(textwrap.wrap(str(title or "Candidate Report"), width=86)[:2])
    wrapped_lines.append("")
    for line in lines:
        text_line = str(line or "").strip()
        if not text_line:
            wrapped_lines.append("")
            continue
        wrapped = textwrap.wrap(text_line, width=86)
        wrapped_lines.extend(wrapped if wrapped else [""])
    wrapped_lines = wrapped_lines[:260]

    stream_lines = ["BT", "/F1 11 Tf", "50 790 Td", "14 TL"]
    for index, line in enumerate(wrapped_lines):
        if index > 0:
            stream_lines.append("T*")
        stream_lines.append(f"({_pdf_escape_text(line)}) Tj")
    stream_lines.append("ET")

    content = "\n".join(stream_lines).encode("latin-1", errors="replace")
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >> endobj",
        b"4 0 obj << /Length %d >> stream\n%s\nendstream endobj" % (len(content), content),
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
    ]

    output = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(output))
        output += obj + b"\n"

    xref_offset = len(output)
    output += f"xref\n0 {len(objects) + 1}\n".encode("ascii")
    output += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        output += f"{off:010d} 00000 n \n".encode("ascii")
    output += (
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return output


def build_admin_candidate_report_pdf(username, display_name, role, feedback, answer_rows, ban_status):
    status_label = "Banned" if ban_status else "Active"
    candidate_label = str(display_name or "").strip() or str(username or "").strip()
    lines = [
        f"Candidate: {candidate_label}",
        f"Login ID: {username}",
        f"Role: {role or 'Not specified'}",
        f"Status: {status_label}",
        f"Questions Evaluated: {len(answer_rows)}",
    ]

    if ban_status:
        lines.append(f"Ban Until: {ban_status.get('ban_until', 'Unknown')}")
        lines.append(f"Ban Reason: {ban_status.get('ban_reason', 'Policy review')}")

    if feedback:
        lines.extend(
            [
                "",
                f"Average Relevance: {feedback.get('avg_relevance', 0.0):.1f}%",
                f"Average Confidence: {feedback.get('avg_confidence', 0.0):.1f}%",
            ]
        )
        if feedback.get("hard_avg_relevance") is not None:
            lines.append(f"Hard Question Relevance: {feedback['hard_avg_relevance']:.1f}%")

        strengths = feedback.get("strengths", [])
        improvements = feedback.get("improvements", [])
        if strengths:
            lines.append("")
            lines.append("Strengths:")
            lines.extend([f"- {item}" for item in strengths[:3]])
        if improvements:
            lines.append("")
            lines.append("Improvement Areas:")
            lines.extend([f"- {item}" for item in improvements[:3]])

    if answer_rows:
        lines.append("")
        lines.append("Answer-by-Answer Snapshot:")
        for row in answer_rows[:20]:
            relevance, confidence = get_row_scores(row)
            lines.append(
                f"Q{row.get('question_no', '')}: {row.get('question_text', '')} | {row.get('result_label', '')} | "
                f"Relevance {relevance:.1f}% | Confidence {confidence:.1f}% | "
                f"Plagiarism {float(_safe_float(row.get('plagiarism_score', 0.0))):.1f}%"
            )

    return _build_simple_pdf("ABC Inc Admin Candidate Report", lines)


def render_fixed_bar_chart(
    dataframe,
    x_field,
    y_field,
    y_title,
    title="",
    color="#0b4db6",
    color_field=None,
    color_scale=None,
    show_value_labels=True,
):
    if dataframe.empty:
        st.info("No data available.")
        return

    chart_data = dataframe[[x_field, y_field]].copy()
    if color_field and color_field in dataframe.columns:
        chart_data[color_field] = dataframe[color_field]
    chart_data["Label"] = chart_data[y_field].apply(_format_chart_label)

    color_encoding = {"value": color}
    if color_field and color_field in chart_data.columns:
        color_encoding = {"field": color_field, "type": "nominal", "legend": {"orient": "top"}}
        if isinstance(color_scale, dict):
            color_encoding["scale"] = color_scale

    layers = [
        {
            "mark": {"type": "bar", "cornerRadiusTopLeft": 4, "cornerRadiusTopRight": 4},
            "encoding": {
                "x": {"field": x_field, "type": "nominal", "sort": "-y", "axis": {"labelAngle": -20}},
                "y": {"field": y_field, "type": "quantitative", "title": y_title},
                "color": color_encoding,
                "tooltip": [
                    {"field": x_field},
                    {"field": y_field, "title": y_title},
                ],
            },
        }
    ]
    if show_value_labels:
        layers.append(
            {
                "mark": {"type": "text", "dy": -7, "fontSize": 11, "fill": "#1b2c4a"},
                "encoding": {
                    "x": {"field": x_field, "type": "nominal", "sort": "-y"},
                    "y": {"field": y_field, "type": "quantitative"},
                    "text": {"field": "Label"},
                },
            }
        )

    st.vega_lite_chart(
        chart_data,
        {
            "autosize": {"type": "fit", "contains": "padding", "resize": True},
            "width": "container",
            "height": 300,
            "title": title,
            "layer": layers,
            "config": {"view": {"stroke": "#dfe8f5"}},
        },
        use_container_width=True,
    )

def render_fixed_line_chart(
    dataframe,
    index_field,
    value_fields,
    title="",
    width=430,
    height=280,
    color_scale=None,
    y_title="Score (%)",
):
    if dataframe.empty:
        st.info("No data available.")
        return

    working = dataframe[[index_field] + value_fields].copy()
    melted = working.melt(id_vars=[index_field], var_name="Metric", value_name="Value")
    melted["ValueLabel"] = melted["Value"].apply(_format_chart_label)
    color_encoding = {"field": "Metric", "type": "nominal", "legend": {"orient": "top"}}
    if isinstance(color_scale, dict):
        color_encoding["scale"] = color_scale

    st.vega_lite_chart(
        melted,
        {
            "autosize": {"type": "fit", "contains": "padding", "resize": True},
            "width": "container",
            "height": int(height),
            "title": title,
            "layer": [
                {
                    "mark": {"type": "line", "point": {"filled": True, "size": 70}},
                    "encoding": {
                        "x": {"field": index_field, "type": "ordinal", "axis": {"labelAngle": -20}},
                        "y": {"field": "Value", "type": "quantitative", "title": y_title},
                        "color": color_encoding,
                        "tooltip": [
                            {"field": index_field},
                            {"field": "Metric"},
                            {"field": "Value"},
                        ],
                    },
                },
                {
                    "mark": {"type": "text", "dy": -10, "fontSize": 10, "fill": "#1a2b48"},
                    "encoding": {
                        "x": {"field": index_field, "type": "ordinal"},
                        "y": {"field": "Value", "type": "quantitative"},
                        "text": {"field": "ValueLabel"},
                    },
                },
            ],
            "config": {"view": {"stroke": "#dfe8f5"}},
        },
        use_container_width=True,
    )


def render_fixed_pie_chart(dataframe, category_field, value_field, title="", color_scale=None):
    if dataframe.empty:
        st.info("No data available.")
        return

    pie_data = dataframe[[category_field, value_field]].copy()
    pie_data[value_field] = pd.to_numeric(pie_data[value_field], errors="coerce").fillna(0.0)
    total = float(pie_data[value_field].sum() or 0.0)
    if total > 0:
        pie_data["Percent"] = pie_data[value_field].apply(lambda value: round(float(value) * 100.0 / total, 1))
    else:
        pie_data["Percent"] = 0.0
    pie_data["PercentLabel"] = pie_data["Percent"].apply(lambda value: f"{value:.1f}%")

    color_encoding = {"field": category_field, "type": "nominal", "legend": {"orient": "right"}}
    if isinstance(color_scale, dict):
        color_encoding["scale"] = color_scale

    st.vega_lite_chart(
        pie_data,
        {
            "autosize": {"type": "fit", "contains": "padding", "resize": True},
            "width": "container",
            "height": 320,
            "title": title,
            "layer": [
                {
                    "mark": {"type": "arc", "innerRadius": 70},
                    "encoding": {
                        "theta": {"field": value_field, "type": "quantitative"},
                        "color": color_encoding,
                        "tooltip": [
                            {"field": category_field},
                            {"field": value_field},
                            {"field": "Percent", "title": "Percent (%)"},
                        ],
                    },
                },
                {
                    "mark": {"type": "text", "radius": 115, "fontSize": 11, "fill": "#102b5e"},
                    "encoding": {
                        "theta": {"field": value_field, "type": "quantitative"},
                        "text": {"field": "PercentLabel"},
                    },
                },
            ],
            "config": {"view": {"stroke": "#dfe8f5"}},
        },
        use_container_width=True,
    )


def build_answer_index(usernames):
    index = {}
    for username in usernames:
        index[str(username)] = get_original_answers(username)
    return index


def candidate_requires_review(answer_rows, is_banned=False):
    if bool(is_banned):
        return True
    for row in answer_rows:
        plagiarism = _safe_float(row.get("plagiarism_score"), 0.0)
        violation_flags = row.get("violation_flags", [])
        if plagiarism >= 10.0 or (isinstance(violation_flags, list) and violation_flags):
            return True
    return False


def build_admin_widget_metrics(df, answer_index, latest_action_map=None):
    if df.empty:
        return {"total_today": 0, "average_score": 0.0, "pending_reviews": 0}

    today = datetime.date.today()
    total_today = 0
    pending_reviews = 0
    total_scores = []
    action_map = latest_action_map or get_latest_admin_action_map(df["username"].tolist())

    for _, row in df.iterrows():
        created_at = _parse_date(row.get("profile_created_at"))
        if created_at == today:
            total_today += 1

        score = _safe_float(row.get("total_score"), 0.0)
        total_scores.append(score)

        username = str(row.get("username", "")).strip()
        answers = answer_index.get(username, [])
        review_resolved = _is_review_resolved_action(action_map.get(username, ""))
        if candidate_requires_review(answers, bool(int(row.get("is_banned", 0) or 0))) and not review_resolved:
            pending_reviews += 1

    average_score = (sum(total_scores) / len(total_scores)) if total_scores else 0.0
    return {
        "total_today": total_today,
        "average_score": round(average_score, 2),
        "pending_reviews": pending_reviews,
    }


def build_role_trend_dataset(df):
    if df.empty:
        return pd.DataFrame(columns=["Role", "Average Score"])
    role_df = (
        df.groupby("applied_role", dropna=False)["total_score"]
        .mean()
        .reset_index()
        .rename(columns={"applied_role": "Role", "total_score": "Average Score"})
    )
    role_df["Average Score"] = role_df["Average Score"].round(2)
    return role_df.sort_values(by="Average Score", ascending=False)


def build_hard_success_dataset(df):
    if df.empty:
        return pd.DataFrame(columns=["Role", "Hard Success Rate"])

    working_df = df.copy()
    working_df["hard_total"] = (
        working_df["correct_hard"].fillna(0)
        + working_df["partial_hard"].fillna(0)
        + working_df["incorrect_hard"].fillna(0)
    )
    working_df["hard_success_rate"] = working_df.apply(
        lambda row: (
            (row["correct_hard"] + row["partial_hard"]) / row["hard_total"] * 100
            if row["hard_total"] > 0
            else 0.0
        ),
        axis=1,
    )
    dataset = (
        working_df.groupby("applied_role", dropna=False)["hard_success_rate"]
        .mean()
        .reset_index()
        .rename(columns={"applied_role": "Role", "hard_success_rate": "Hard Success Rate"})
    )
    dataset["Hard Success Rate"] = dataset["Hard Success Rate"].round(1)
    return dataset.sort_values(by="Hard Success Rate", ascending=False)


def build_candidate_comparison_card(username, score, answers):
    feedback = build_feedback_summary(answers)
    avg_relevance = feedback["avg_relevance"] if feedback else 0.0
    avg_confidence = feedback["avg_confidence"] if feedback else 0.0
    counts = feedback["label_counts"] if feedback else {"Correct": 0, "Partially Correct": 0, "Incorrect": 0}
    return {
        "Candidate": username,
        "Score": score,
        "Avg Relevance": round(avg_relevance, 1),
        "Avg Confidence": round(avg_confidence, 1),
        "Correct": int(counts.get("Correct", 0)),
        "Partial": int(counts.get("Partially Correct", 0)),
        "Incorrect": int(counts.get("Incorrect", 0)),
    }


def _normalize_keywords(values):
    if not isinstance(values, list):
        return []
    normalized = []
    for value in values:
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
    return normalized


def _audit_row_style(row):
    action = str(row.get("Action") or row.get("action") or "").strip().upper()
    if action.startswith("BAN"):
        bg = "#fee2e2"
        fg = "#7f1d1d"
    elif action.startswith("UNBAN") or "SCHEDULE" in action:
        bg = "#dcfce7"
        fg = "#14532d"
    elif "SEND_FEEDBACK" in action:
        bg = "#dbeafe"
        fg = "#1e3a8a"
    else:
        bg = "#f1f5f9"
        fg = "#0f172a"
    return [f"background-color: {bg}; color: {fg};" for _ in row]


def get_row_scores(item):
    result_label = str(item.get("result_label", "")).strip()
    has_relevance = "relevance_score" in item and item.get("relevance_score") not in (None, "")
    has_confidence = "confidence_score" in item and item.get("confidence_score") not in (None, "")

    fallback_map = {
        "Correct": (85.0, 75.0),
        "Partially Correct": (55.0, 60.0),
        "Incorrect": (25.0, 50.0),
    }

    relevance = _safe_float(item.get("relevance_score"), 0.0)
    confidence = _safe_float(item.get("confidence_score"), 0.0)

    if not has_relevance and result_label in fallback_map:
        relevance = fallback_map[result_label][0]
    if not has_confidence and result_label in fallback_map:
        confidence = fallback_map[result_label][1]

    return round(relevance, 1), round(confidence, 1)


def build_feedback_summary(answer_rows):
    if not answer_rows:
        return None

    topic_stats = {}
    label_counts = {"Correct": 0, "Partially Correct": 0, "Incorrect": 0}
    total_relevance = 0.0
    total_confidence = 0.0
    hard_relevance_total = 0.0
    hard_count = 0

    for row in answer_rows:
        result_label = str(row.get("result_label", "")).strip()
        if result_label in label_counts:
            label_counts[result_label] += 1

        topic = str(row.get("topic") or "General").strip() or "General"
        difficulty = str(row.get("difficulty", "")).strip().lower()
        relevance, confidence = get_row_scores(row)
        missing_keywords = _normalize_keywords(row.get("missing_keywords", []))

        total_relevance += relevance
        total_confidence += confidence

        if difficulty == "hard":
            hard_relevance_total += relevance
            hard_count += 1

        stats = topic_stats.setdefault(
            topic,
            {
                "count": 0,
                "relevance_total": 0.0,
                "confidence_total": 0.0,
                "hard_count": 0,
                "hard_relevance_total": 0.0,
                "missing": {},
            },
        )

        stats["count"] += 1
        stats["relevance_total"] += relevance
        stats["confidence_total"] += confidence

        if difficulty == "hard":
            stats["hard_count"] += 1
            stats["hard_relevance_total"] += relevance

        for keyword in missing_keywords:
            stats["missing"][keyword] = stats["missing"].get(keyword, 0) + 1

    topic_analysis = []
    strengths = []
    improvements = []

    for topic, stats in topic_stats.items():
        count = max(stats["count"], 1)
        avg_relevance = stats["relevance_total"] / count
        avg_confidence = stats["confidence_total"] / count
        hard_avg = (stats["hard_relevance_total"] / stats["hard_count"]) if stats["hard_count"] else None

        sorted_missing = sorted(stats["missing"].items(), key=lambda item: (-item[1], item[0]))
        top_missing = [keyword for keyword, _ in sorted_missing[:3]]

        topic_analysis.append(
            {
                "Topic": topic,
                "Questions": stats["count"],
                "Avg Relevance (%)": round(avg_relevance, 1),
                "Avg Confidence (%)": round(avg_confidence, 1),
                "Hard Q Relevance (%)": round(hard_avg, 1) if hard_avg is not None else float("nan"),
                "Top Missing Keywords": ", ".join(top_missing) if top_missing else "-",
            }
        )

        if avg_relevance >= 70 and avg_confidence >= 60:
            strengths.append(
                f"{topic}: strong answers with {avg_relevance:.1f}% relevance and {avg_confidence:.1f}% confidence."
            )

        if avg_relevance < 60:
            if top_missing:
                improvements.append(f"{topic}: great start. Consider adding {', '.join(top_missing)} to strengthen answers.")
            else:
                improvements.append(f"{topic}: great effort. Consider adding more depth and clarity.")

    topic_analysis.sort(key=lambda item: item["Avg Relevance (%)"], reverse=True)

    if not strengths:
        if topic_analysis:
            strengths.append(
                f"{topic_analysis[0]['Topic']}: currently strongest area among attempted topics."
            )
        else:
            strengths.append("Candidate attempted interview; baseline established for growth.")

    if not improvements:
        improvements.append("Great consistency so far. Consider deeper hard-question coverage for the next level.")

    avg_relevance = total_relevance / len(answer_rows)
    avg_confidence = total_confidence / len(answer_rows)
    hard_avg_relevance = (hard_relevance_total / hard_count) if hard_count else None

    top_missing_keywords = []
    for row in topic_analysis:
        raw_keywords = row["Top Missing Keywords"]
        if raw_keywords and raw_keywords != "-":
            for keyword in [item.strip() for item in raw_keywords.split(",") if item.strip()]:
                if keyword not in top_missing_keywords:
                    top_missing_keywords.append(keyword)

    return {
        "question_count": len(answer_rows),
        "avg_relevance": round(avg_relevance, 1),
        "avg_confidence": round(avg_confidence, 1),
        "hard_avg_relevance": round(hard_avg_relevance, 1) if hard_avg_relevance is not None else None,
        "label_counts": label_counts,
        "strengths": strengths[:3],
        "improvements": improvements[:3],
        "topic_analysis": topic_analysis,
        "top_missing_keywords": top_missing_keywords[:5],
    }


def show_answers_and_insights(username):
    st.markdown("<div class='breadcrumbs'>Control Center &rsaquo; Talent Hub &rsaquo; Review</div>", unsafe_allow_html=True)

    attempt_rows = get_candidate_interview_attempts(username)
    selected_attempt_id = None
    if attempt_rows:
        attempt_state_key = f"admin_selected_attempt_id_{username}"
        valid_attempt_ids = [attempt["id"] for attempt in attempt_rows]
        if st.session_state.get(attempt_state_key) not in valid_attempt_ids:
            st.session_state[attempt_state_key] = valid_attempt_ids[0]

        default_index = next(
            (
                index
                for index, attempt in enumerate(attempt_rows)
                if attempt["id"] == st.session_state[attempt_state_key]
            ),
            0,
        )
        selected_label = st.selectbox(
            "Interview Attempt",
            options=[attempt["label"] for attempt in attempt_rows],
            index=default_index,
            key=f"admin_attempt_picker_{username}",
        )
        selected_attempt = next((attempt for attempt in attempt_rows if attempt["label"] == selected_label), attempt_rows[0])
        selected_attempt_id = selected_attempt["id"]
        st.session_state[attempt_state_key] = selected_attempt_id
        st.caption(
            f"Showing attempt {selected_attempt['sequence_no']} of {len(attempt_rows)} "
            f"({selected_attempt['timestamp_label']})."
        )
    else:
        st.info("No interview attempts found for this candidate yet.")

    with st.spinner("Loading candidate insights..."):
        answers = get_original_answers(username, interview_id=selected_attempt_id)
        feedback = build_feedback_summary(answers) if answers else None
        ban_status = get_active_ban_status(username)
        selected_snapshot = get_interview_result_snapshot(username, interview_id=selected_attempt_id)
        candidate_role = (
            str((selected_snapshot or {}).get("role", "")).strip()
            or get_latest_candidate_role(username)
            or st.session_state.get("admin_selected_role", "")
        )
        profile_snapshot = get_latest_candidate_profile_snapshot(username)
        interview_result = get_latest_interview_score(username, interview_id=selected_attempt_id)
        display_name = str(profile_snapshot.get("display_name") or "").strip() or str(username or "").strip()
        report_pdf = build_admin_candidate_report_pdf(
            username,
            display_name,
            candidate_role,
            feedback,
            answers,
            ban_status,
        )

    status_text = "Banned" if ban_status else "Active"
    status_css = "banned" if ban_status else "active"
    avatar_text = _escape_html((str(display_name or username or "?").strip()[:1] or "?").upper())

    ai_confirm_key = f"confirm_ai_ban_{username}"
    plagiarism_confirm_key = f"confirm_plag_ban_{username}"
    unban_confirm_key = f"confirm_unban_{username}"
    for key in [ai_confirm_key, plagiarism_confirm_key, unban_confirm_key]:
        if key not in st.session_state:
            st.session_state[key] = False

    st.markdown(
        f"""
<a id="candidate-info"></a>
<div class="summary-card">
  <div class="summary-header">
    <div class="candidate-avatar">{avatar_text}</div>
    <div>
      <div style="font-size:20px;font-weight:700;">Quick Profile</div>
      <div class="summary-subtitle">Live profile, score state, and review status</div>
    </div>
  </div>
  <div class="summary-grid">
    <div class="summary-item"><div class="summary-label">Name</div><div class="summary-value">{_escape_html(display_name)}</div></div>
    <div class="summary-item"><div class="summary-label">Role</div><div class="summary-value">{_escape_html(candidate_role)}</div></div>
    <div class="summary-item"><div class="summary-label">Interview Result</div><div class="summary-value">{_escape_html(interview_result)}</div></div>
    <div class="summary-item"><div class="summary-label">Status</div><div class="summary-value"><span class="status-pill {status_css}">{status_text}</span></div></div>
  </div>
  <div class="summary-grid">
    <div class="summary-item"><div class="summary-label">Phone Number</div><div class="summary-value">{_escape_html(profile_snapshot["phone"])}</div></div>
    <div class="summary-item"><div class="summary-label">Email ID</div><div class="summary-value">{_escape_html(profile_snapshot["email"])}</div></div>
    <div class="summary-item"><div class="summary-label">Experience</div><div class="summary-value">{_escape_html(profile_snapshot["experience"])}</div></div>
    <div class="summary-item"><div class="summary-label">Previous Job Role</div><div class="summary-value">{_escape_html(profile_snapshot["previous_role"])}</div></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    multi_interview_insights = get_candidate_multi_interview_insights(username)
    with st.container(border=True):
        st.markdown("#### Performance Across Interviews")
        st.caption(f"Total interviews completed: {multi_interview_insights['total_attempts']}")
        role_insight_rows = multi_interview_insights.get("role_insights", [])
        if role_insight_rows:
            table_rows = [{key: value for key, value in row.items() if key != "Suggestion"} for row in role_insight_rows]
            table_df = pd.DataFrame(table_rows)
            table_df.index = table_df.index + 1
            st.dataframe(table_df, width="stretch")
            st.markdown("**Role-wise Suggestions**")
            role_emoji_map = {
                "Developer": "💻",
                "Tester": "🧪",
                "Analyst": "📊",
            }
            for row in role_insight_rows:
                role_name = str(row.get("Role", "")).strip()
                role_emoji = role_emoji_map.get(role_name, "•")
                st.markdown(f"{role_emoji} **{role_name}:**  \n{row['Suggestion']}")
            if multi_interview_insights.get("all_roles_covered"):
                st.success("Candidate has completed interviews across Developer, Tester, and Analyst roles.")
        else:
            st.info("Cross-interview insights will appear after additional interview attempts.")

    with st.container(border=True):
        st.markdown("#### Decision Tools")
        st.caption("Use enforcement controls first. Workflow actions are unlocked after checklist completion.")
        action_col1, action_col2, action_col3 = st.columns(3)
        with action_col1:
            if st.button(
                "Ban Candidate for AI",
                key=f"admin_ban_ai_{username}",
                disabled=bool(ban_status),
                type="primary",
                help="Use after manual review when AI-generated answer patterns are confirmed.",
            ):
                st.session_state[ai_confirm_key] = True
                st.session_state[plagiarism_confirm_key] = False
                st.session_state[unban_confirm_key] = False
                st.rerun()
        with action_col2:
            if st.button(
                "Ban Candidate for Plagiarism",
                key=f"admin_ban_plagiarism_{username}",
                disabled=bool(ban_status),
                type="primary",
                help="Use after manual review when copied content is confirmed.",
            ):
                st.session_state[plagiarism_confirm_key] = True
                st.session_state[ai_confirm_key] = False
                st.session_state[unban_confirm_key] = False
                st.rerun()
        with action_col3:
            if st.button(
                "Unban Candidate",
                key=f"admin_unban_{username}",
                disabled=not bool(ban_status),
                type="tertiary",
                help="Use when prior ban evidence is resolved after review.",
            ):
                st.session_state[unban_confirm_key] = True
                st.session_state[ai_confirm_key] = False
                st.session_state[plagiarism_confirm_key] = False
                st.rerun()
        if st.session_state.get(ai_confirm_key):
            st.warning("Confirm AI ban? This will ban the candidate for 1 year.")
            confirm_ai_col1, confirm_ai_col2 = st.columns(2)
            with confirm_ai_col1:
                if st.button("Confirm AI Ban", key=f"confirm_ai_ban_button_{username}"):
                    details = ban_candidate_from_admin(username, ADMIN_AI_BAN_REASON, actor="Admin")
                    st.session_state[ai_confirm_key] = False
                    st.success(f"Candidate banned until {details['ban_until']} (AI review).")
                    st.rerun()
            with confirm_ai_col2:
                if st.button("Cancel", key=f"cancel_ai_ban_button_{username}"):
                    st.session_state[ai_confirm_key] = False
                    st.rerun()

        if st.session_state.get(plagiarism_confirm_key):
            st.warning("Confirm plagiarism ban? This will ban the candidate for 1 year.")
            confirm_plag_col1, confirm_plag_col2 = st.columns(2)
            with confirm_plag_col1:
                if st.button("Confirm Plagiarism Ban", key=f"confirm_plagiarism_ban_button_{username}"):
                    details = ban_candidate_from_admin(username, ADMIN_PLAGIARISM_BAN_REASON, actor="Admin")
                    st.session_state[plagiarism_confirm_key] = False
                    st.success(f"Candidate banned until {details['ban_until']} (plagiarism review).")
                    st.rerun()
            with confirm_plag_col2:
                if st.button("Cancel", key=f"cancel_plagiarism_ban_button_{username}"):
                    st.session_state[plagiarism_confirm_key] = False
                    st.rerun()

        if st.session_state.get(unban_confirm_key):
            st.info("Confirm unban? This clears ban flags for the candidate.")
            confirm_unban_col1, confirm_unban_col2 = st.columns(2)
            with confirm_unban_col1:
                if st.button("Confirm Unban", key=f"confirm_unban_button_{username}"):
                    unban_candidate_from_admin(username, actor="Admin")
                    st.session_state[unban_confirm_key] = False
                    st.success("Candidate has been unbanned.")
                    st.rerun()
            with confirm_unban_col2:
                if st.button("Cancel", key=f"cancel_unban_button_{username}"):
                    st.session_state[unban_confirm_key] = False
                    st.rerun()

    if not answers:
        st.info("No stored original answers found for this candidate.")
        return

    st.markdown('<a id="suggestions"></a>', unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader("Smart Insights")
        if feedback:
            insight_col1, insight_col2 = st.columns(2)
            with insight_col1:
                st.markdown("✅ **Strengths**")
                for strength in feedback.get("strengths", [])[:3]:
                    st.write(f"- {strength}")
            with insight_col2:
                st.markdown("⚠️ **Improvement Areas**")
                for improvement in feedback.get("improvements", [])[:3]:
                    st.write(f"- {improvement}")
        else:
            st.info("Smart insights will appear after interview responses are available.")

    tab_overview, tab_scores, tab_suggestions = st.tabs(
        ["Interview Summary", "Assessment Results", "Growth Tips"]
    )

    with tab_overview:
        st.markdown('<a id="scores"></a>', unsafe_allow_html=True)
        if feedback:
            metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
            with metric_col1:
                st.metric("Questions", feedback["question_count"])
            with metric_col2:
                st.metric("Avg Relevance", f"{feedback['avg_relevance']:.1f}%")
            with metric_col3:
                st.metric("Avg Confidence", f"{feedback['avg_confidence']:.1f}%")
            with metric_col4:
                hard_relevance_text = "N/A"
                if feedback["hard_avg_relevance"] is not None:
                    hard_relevance_text = f"{feedback['hard_avg_relevance']:.1f}%"
                st.metric("Hard Q Relevance", hard_relevance_text)

            counts = feedback["label_counts"]
            counts_df = pd.DataFrame(
                [
                    {"Result": "Correct", "Count": counts["Correct"]},
                    {"Result": "Partially Correct", "Count": counts["Partially Correct"]},
                    {"Result": "Incorrect", "Count": counts["Incorrect"]},
                ]
            )
            render_fixed_bar_chart(
                counts_df,
                "Result",
                "Count",
                "Questions",
                "Result Distribution",
                color_field="Result",
                color_scale={
                    "domain": ["Correct", "Partially Correct", "Incorrect"],
                    "range": ["#2e7d32", "#0b4db6", "#c62828"],
                },
            )

            if feedback["topic_analysis"]:
                st.markdown("**Keyword Insights**")
                keyword_df = pd.DataFrame(feedback["topic_analysis"])
                keyword_df.index = keyword_df.index + 1
                st.dataframe(keyword_df, width="stretch")

            if feedback["top_missing_keywords"]:
                chips = "".join(
                    [f"<span class='keyword-chip warning'>{_escape_html(keyword)}</span>" for keyword in feedback["top_missing_keywords"]]
                )
                st.markdown(
                    f"<div class='keyword-chip-row'><strong>Frequently missed keywords:</strong> {chips}</div>",
                    unsafe_allow_html=True,
                )

    with tab_scores:
        score_rows = []
        for item in answers:
            scoring_breakdown = item.get("scoring_breakdown", {})
            if not isinstance(scoring_breakdown, dict):
                scoring_breakdown = {}
            relevance, confidence = get_row_scores(item)
            score_rows.append(
                {
                    "Question": f"Q{item.get('question_no', '')}",
                    "Result": item.get("result_label", ""),
                    "Relevance": relevance,
                    "Confidence": confidence,
                    "Coverage": _safe_float(scoring_breakdown.get("coverage"), 0.0),
                    "Semantic Similarity": _safe_float(scoring_breakdown.get("semantic_similarity"), 0.0),
                    "Length Quality": _safe_float(scoring_breakdown.get("length_quality"), 0.0),
                    "Plagiarism Risk": _safe_float(item.get("plagiarism_score"), 0.0),
                }
            )
        score_df = pd.DataFrame(score_rows)
        score_df.index = score_df.index + 1
        st.dataframe(score_df, width="stretch")
        if not score_df.empty:
            render_fixed_line_chart(
                score_df,
                "Question",
                ["Relevance", "Confidence"],
                "Relevance vs Confidence by Question",
                width=860,
                height=320,
                color_scale={"domain": ["Relevance", "Confidence"], "range": ["#0b4db6", "#2e7d32"]},
            )
            render_fixed_bar_chart(
                score_df,
                "Question",
                "Plagiarism Risk",
                "Risk (%)",
                "Plagiarism Risk by Question",
                color="#a61e1e",
            )

    with tab_suggestions:
        if feedback:
            st.markdown("✅ **Strengths**")
            for strength in feedback["strengths"]:
                st.write(f"- {strength}")

            st.markdown("⚠️ **Improvement Areas**")
            for improvement in feedback["improvements"]:
                st.write(f"- {improvement}")

        for item in answers:
            improvement_insights = item.get("improvement_insights", [])
            if not isinstance(improvement_insights, list):
                improvement_insights = []
            improvement_insights = [str(value).strip() for value in improvement_insights if str(value).strip()]
            if not improvement_insights:
                improvement_insights = [
                    "Great start! Consider structuring it as Definition -> Mechanism -> Practical Impact."
                ]
            missed_keywords = _normalize_keywords(item.get("missing_keywords", []))

            with st.expander(f"Q{item.get('question_no', '')}. Guided Suggestions", expanded=False):
                st.caption("Missed Keywords: " + (", ".join(missed_keywords) if missed_keywords else "None"))
                for suggestion in improvement_insights[:4]:
                    st.write(f"- {suggestion}")

    st.markdown("#### Response Breakdown")
    for item in answers:
        question_no = item.get("question_no", "")
        question_text = item.get("question_text", "")
        answer_text = item.get("answer_text", "")
        result_label = item.get("result_label", "")
        difficulty = item.get("difficulty", "")
        topic = str(item.get("topic") or "General").strip() or "General"
        relevance, confidence = get_row_scores(item)
        plagiarism_score = _safe_float(item.get("plagiarism_score"), 0.0)

        matched_keywords = _normalize_keywords(item.get("matched_keywords", []))
        missing_keywords = _normalize_keywords(item.get("missing_keywords", []))
        scoring_breakdown = item.get("scoring_breakdown", {})
        if not isinstance(scoring_breakdown, dict):
            scoring_breakdown = {}
        coverage = _safe_float(scoring_breakdown.get("coverage"), 0.0)
        semantic_similarity = _safe_float(scoring_breakdown.get("semantic_similarity"), 0.0)
        length_quality = _safe_float(scoring_breakdown.get("length_quality"), 0.0)

        violation_flags = item.get("violation_flags", [])
        if not isinstance(violation_flags, list):
            violation_flags = []
        violation_flags = [str(value).strip() for value in violation_flags if str(value).strip()]

        with st.expander(f"Q{question_no}. {question_text}", expanded=False):
            st.write(f"Answer: {answer_text if answer_text else '(No answer provided)'}")
            audio_bytes = decode_audio_blob(item.get("audio_base64", ""))
            audio_mime = item.get("audio_mime", "audio/wav")
            if audio_bytes:
                st.caption("Recorded Answer Audio:")
                st.audio(audio_bytes, format=audio_mime)

            result_line = _escape_html(f"{result_label} | Difficulty: {difficulty} | Topic: {topic}")
            relevance_line = _escape_html(f"{relevance:.1f}% | Confidence: {confidence:.1f}%")
            coverage_line = _escape_html(
                f"{coverage:.1f}% | Semantic Similarity: {semantic_similarity:.1f}% | Length Quality: {length_quality:.1f}%"
            )
            risk_line = _escape_html(f"{plagiarism_score:.1f}%")
            matched_line = _escape_html(", ".join(matched_keywords) if matched_keywords else "None")
            missed_line = _escape_html(", ".join(missing_keywords) if missing_keywords else "None")

            st.markdown(
                f"""
<div style="font-size: 15px; line-height: 1.5; color: var(--text-primary); margin-top: 0.35rem;">
  <div style="font-weight: 600;">🧾 Result: {result_line}</div>
  <div style="font-weight: 600; margin-top: 0.2rem;">📊 Relevance: {relevance_line}</div>
  <div style="font-weight: 600; margin-top: 0.2rem;">🧠 Coverage: {coverage_line}</div>
  <div style="font-weight: 600; margin-top: 0.2rem;">🚨 Plagiarism Risk: {risk_line}</div>
  <div style="font-weight: 600; margin-top: 0.2rem;">✅ Matched Keywords: {matched_line}</div>
  <div style="font-weight: 600; margin-top: 0.2rem;">🧩 Missed Keywords: {missed_line}</div>
</div>
""",
                unsafe_allow_html=True,
            )

            if violation_flags:
                st.error("Policy Flags: " + ", ".join(violation_flags))

    st.markdown('<a id="final-note"></a>', unsafe_allow_html=True)
    st.markdown("#### Completion Checklist")
    checklist_items = [
        "I reviewed plagiarism indicators and keyword coverage.",
        "I selected and recorded the next action for this candidate.",
    ]
    checklist_keys = []
    for index, item in enumerate(checklist_items, start=1):
        check_key = f"admin_review_check_{username}_{index}"
        checklist_keys.append(check_key)
        st.checkbox(item, key=check_key)

    checklist_complete = bool(checklist_keys) and all(bool(st.session_state.get(key)) for key in checklist_keys)
    if checklist_complete:
        st.success("Review checklist completed. You can proceed with workflow actions.")
    else:
        st.caption("Complete this checklist to finalize review quality.")

    st.markdown("#### Closing Actions")
    st.caption("These actions unlock after completion of the checklist above.")
    closing_col1, closing_col2, closing_col3 = st.columns(3)
    with closing_col1:
        st.download_button(
            "Download Candidate Report",
            data=report_pdf,
            file_name=f"{username}_admin_candidate_report.pdf",
            mime="application/pdf",
            key=f"admin_download_report_{username}",
        )
    with closing_col2:
        if st.button("Schedule Next Round", key=f"schedule_next_{username}", disabled=not checklist_complete):
            log_admin_action(username, "SCHEDULE_NEXT_ROUND", "Candidate moved to next stage.", "Admin")
            st.success("Next round scheduling has been recorded in the action log.")
            st.rerun()
    with closing_col3:
        if st.button("Send Feedback", key=f"send_feedback_{username}", disabled=not checklist_complete):
            log_admin_action(username, "SEND_FEEDBACK", "Feedback request sent to candidate.", "Admin")
            st.success("Feedback action has been recorded in the action log.")
            st.rerun()


st.set_page_config(page_title="Control Center", layout="wide", initial_sidebar_state="collapsed")
admin_wallpaper_uri = _file_data_uri(r"D:\Interview bot\Copilot_20260318_112026.png")
if not admin_wallpaper_uri:
    admin_wallpaper_uri = _file_data_uri("Copilot_20260318_112026.png")

if admin_wallpaper_uri:
    admin_background_css = (
        "background: linear-gradient(135deg, rgba(18, 40, 70, 0.34) 0%, rgba(23, 52, 86, 0.38) 55%, "
        f"rgba(19, 43, 73, 0.42) 100%), url('{admin_wallpaper_uri}') center center / cover no-repeat !important;"
    )
else:
    admin_background_css = (
        "background: radial-gradient(circle at 8% 15%, rgba(24, 169, 153, 0.08) 0%, rgba(24, 169, 153, 0) 36%), "
        "radial-gradient(circle at 86% 0%, rgba(11, 77, 182, 0.12) 0%, rgba(11, 77, 182, 0) 42%), "
        "linear-gradient(180deg, #f7faff 0%, #ffffff 70%) !important;"
    )

st.markdown(
    """
<style>
[data-testid="stAppViewContainer"] {
    __ADMIN_BG__
}

[data-testid="stAppViewContainer"] .main {
    background: transparent !important;
}

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
    --card-border: #334862;
}

html, body, [class*="css"] {
    font-family: "Inter", "Roboto", Arial, sans-serif;
    color: var(--text-primary);
}

h1, h2, h3, h4 {
    font-family: "Roboto", "Inter", Arial, sans-serif;
    color: var(--text-primary);
}

.brand-bar {
    background: linear-gradient(135deg, var(--brand-primary) 0%, #2f8be6 100%);
    color: #fff;
    border-radius: 16px;
    padding: 16px 20px;
    margin: 0 auto 18px auto !important;
    max-width: 520px;
    box-shadow: 0 10px 26px rgba(12, 45, 95, 0.16);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: 10px;
}

.brand-logo {
    width: 74px;
    height: 74px;
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
    font-family: "Roboto", Arial, sans-serif;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    font-weight: 700;
    font-size: 22px;
    line-height: 1.1;
}

.brand-subtitle {
    font-size: 13px;
    margin-top: 6px;
    opacity: 0.95;
}

.admin-login-shell {
    max-width: 860px;
    margin: 5vh auto 0 auto;
    text-align: center;
}

.admin-login-logo {
    display: inline-flex;
    align-items: baseline;
    font-family: "Roboto", "Inter", Arial, sans-serif;
    font-size: 78px;
    font-weight: 700;
    color: #163a67;
    letter-spacing: 0.02em;
    text-shadow: 0 2px 12px rgba(40, 74, 118, 0.18);
}

.admin-login-logo .inc {
    font-size: 16px;
    margin-left: 10px;
    opacity: 0.8;
}

.admin-login-title {
    margin-top: 10px;
    margin-bottom: 26px;
    font-size: 46px;
    font-weight: 700;
    color: #f4f8ff;
    text-shadow: 0 2px 8px rgba(3, 10, 25, 0.4);
}

.admin-login-subtitle {
    margin-top: 2px;
    margin-bottom: 8px;
    font-size: 30px;
    font-weight: 600;
    color: #163a67;
}

.admin-login-note {
    font-size: 16px;
    color: #476a96;
    margin-bottom: 20px;
}

html[data-theme="dark"] .admin-login-logo,
html[data-theme="dark"] .admin-login-title,
html[data-theme="dark"] .admin-login-subtitle,
html[data-theme="dark"] .admin-login-note {
    color: #f6f9ff;
}

.breadcrumbs {
    color: #294974;
    font-size: 13px;
    font-weight: 500;
    margin: 2px 0 10px 0;
}

html[data-theme="dark"] .breadcrumbs {
    color: #c6d7f2;
}

.sidebar-nav {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 8px 0 4px 0;
}

.sidebar-filter-btn {
    display: block;
    text-decoration: none !important;
    color: #0b3f89 !important;
    border: 1px solid #bfd3f3;
    border-radius: 12px;
    padding: 10px 12px;
    font-family: "Trebuchet MS", "Segoe UI", "Segoe UI Emoji", Arial, sans-serif;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.01em;
    background: linear-gradient(180deg, #f4f9ff 0%, #e3eeff 100%);
    box-shadow: 0 2px 0 #cfe1fc, 0 5px 14px rgba(11, 63, 137, 0.14);
    transition: transform 0.12s ease, box-shadow 0.16s ease, background 0.16s ease;
}

.sidebar-filter-btn:hover {
    background: linear-gradient(180deg, #fbfdff 0%, #edf5ff 100%);
    box-shadow: 0 3px 0 #cfe1fc, 0 8px 16px rgba(11, 63, 137, 0.2);
    transform: translateY(-1px);
}

.sidebar-filter-btn:active {
    transform: translateY(1px) scale(0.99);
    box-shadow: 0 1px 0 #cfe1fc, 0 3px 8px rgba(11, 63, 137, 0.16);
}

.sidebar-filter-btn:focus-visible {
    outline: 2px solid #2f7de8;
    outline-offset: 2px;
}

html[data-theme="dark"] .sidebar-filter-btn {
    color: #e5eeff !important;
    border-color: #4f6789;
    background: linear-gradient(180deg, #23334d 0%, #1b273e 100%);
    box-shadow: 0 2px 0 #334a6a, 0 5px 14px rgba(10, 20, 35, 0.45);
}

html[data-theme="dark"] .sidebar-filter-btn:hover {
    background: linear-gradient(180deg, #2a3d5c 0%, #22314c 100%);
    box-shadow: 0 3px 0 #3b557a, 0 8px 16px rgba(10, 20, 35, 0.55);
}

.main-panel-label {
    font-size: 14px;
    font-weight: 700;
    color: #0b4db6;
    line-height: 1.5;
}

html[data-theme="dark"] .main-panel-label {
    color: #7cb4ff;
}

section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label,
section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label span,
section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label p {
    color: #0f172a !important;
    opacity: 1 !important;
}

html[data-theme="dark"] section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label,
html[data-theme="dark"] section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label span,
html[data-theme="dark"] section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label p {
    color: #ffffff !important;
}

section[data-testid="stSidebar"] div[data-baseweb="checkbox"] label,
section[data-testid="stSidebar"] div[data-baseweb="checkbox"] label *,
section[data-testid="stSidebar"] div[data-baseweb="checkbox"] span,
section[data-testid="stSidebar"] div[data-baseweb="checkbox"] div {
    color: #ffffff !important;
    opacity: 1 !important;
    font-weight: 600;
}

html[data-theme="dark"] section[data-testid="stSidebar"] div[data-baseweb="checkbox"] label,
html[data-theme="dark"] section[data-testid="stSidebar"] div[data-baseweb="checkbox"] label *,
html[data-theme="dark"] section[data-testid="stSidebar"] div[data-baseweb="checkbox"] span,
html[data-theme="dark"] section[data-testid="stSidebar"] div[data-baseweb="checkbox"] div {
    color: #ffffff !important;
}

section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label,
section[data-testid="stSidebar"] div[data-testid="stCheckbox"] label *,
section[data-testid="stSidebar"] div[data-testid="stCheckbox"] p,
section[data-testid="stSidebar"] div[data-testid="stCheckbox"] span {
    color: #ffffff !important;
    opacity: 1 !important;
}

.summary-card {
    background: linear-gradient(115deg, #083a89 0%, #0b4db6 45%, #1a6fd1 100%);
    border-radius: 16px;
    color: #fff;
    padding: 16px 18px;
    margin-bottom: 12px;
    box-shadow: 0 10px 26px rgba(12, 45, 95, 0.14);
}

.summary-header {
    display: flex;
    align-items: center;
    gap: 12px;
}

.candidate-avatar {
    width: 54px;
    height: 54px;
    border-radius: 999px;
    border: 2px solid rgba(255, 255, 255, 0.6);
    background: rgba(255, 255, 255, 0.2);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    font-weight: 700;
}

.summary-subtitle {
    margin-top: 3px;
    font-size: 12px;
    opacity: 0.9;
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

.status-pill {
    display: inline-block;
    border-radius: 999px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: 600;
}

.status-pill.active {
    color: #145d2e;
    background: #e6f7eb;
}

.status-pill.banned {
    color: #8a1e1e;
    background: #fdeaea;
}

.keyword-chip-row {
    margin-top: 8px;
    margin-bottom: 8px;
}

.keyword-chip {
    display: inline-block;
    padding: 4px 8px;
    border-radius: 999px;
    font-size: 12px;
    margin: 4px 6px 0 0;
    background: #eaf1ff;
    color: #1d3d71;
    border: 1px solid #c9d9f3;
}

.keyword-chip.warning {
    background: #fff3e2;
    color: #915100;
    border: 1px solid #f4cc98;
}

.compare-card {
    background: #eef5ff;
    border: 1px solid #d7e7ff;
    border-radius: 10px;
    padding: 8px 10px;
}

.compare-card-label {
    color: #294974;
    opacity: 1;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
}

.compare-card-value {
    color: #12223a;
    font-size: 16px;
    font-weight: 700;
    margin-top: 1px;
}

html[data-theme="dark"] .compare-card {
    background: #1f2f48;
    border-color: #476185;
}

html[data-theme="dark"] .compare-card-label {
    color: #cedcf3;
}

html[data-theme="dark"] .compare-card-value {
    color: #f1f6ff;
}

[data-testid="stDataFrame"] [role="columnheader"] {
    color: var(--text-primary) !important;
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

div[data-testid="stCheckbox"] label,
div[data-testid="stRadio"] label {
    opacity: 1 !important;
}

[data-testid="stDataFrame"] [role="columnheader"] {
    background-color: rgba(11, 77, 182, 0.08) !important;
}

html[data-theme="dark"] [data-testid="stDataFrame"] [role="columnheader"] {
    background-color: rgba(74, 108, 156, 0.36) !important;
}

.stButton > button {
    background: var(--brand-primary);
    color: #fff;
    border: 0;
    border-radius: 10px;
    font-weight: 600;
    transition: transform 0.16s ease, box-shadow 0.16s ease, background-color 0.16s ease;
}

.stButton > button:hover {
    background: var(--brand-primary-strong);
    transform: translateY(-1px);
    box-shadow: 0 6px 14px rgba(11, 77, 182, 0.24);
}

div[data-testid="stDownloadButton"] > button {
    background: #0f766e !important;
    border: 1px solid #0f766e !important;
    color: #ffffff !important;
}

div[data-testid="stDownloadButton"] > button:hover {
    background: #0a5e58 !important;
    border: 1px solid #0a5e58 !important;
}

div[data-testid="stButton"] button[aria-label*="ban candidate for ai" i],
div[data-testid="stButton"] button[aria-label*="ban candidate for plagiarism" i],
div[data-testid="stButton"] button[kind="primary"] {
    background: #c62828 !important;
    border: 1px solid #c62828 !important;
    color: #ffffff !important;
}

div[data-testid="stButton"] button[aria-label*="ban candidate for ai" i]:hover,
div[data-testid="stButton"] button[aria-label*="ban candidate for plagiarism" i]:hover,
div[data-testid="stButton"] button[kind="primary"]:hover {
    background: #a61e1e !important;
    border: 1px solid #a61e1e !important;
}

div[data-testid="stButton"] button[aria-label*="unban candidate" i],
div[data-testid="stButton"] button[kind="tertiary"] {
    background: #2e7d32 !important;
    border: 1px solid #2e7d32 !important;
    color: #ffffff !important;
}

div[data-testid="stButton"] button[aria-label*="unban candidate" i]:hover,
div[data-testid="stButton"] button[kind="tertiary"]:hover {
    background: #236528 !important;
    border: 1px solid #236528 !important;
}

@media (max-width: 960px) {
    .brand-bar {
        padding: 14px 16px;
    }
    .summary-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .summary-header {
        align-items: flex-start;
    }
}
</style>
""".replace("__ADMIN_BG__", admin_background_css),
    unsafe_allow_html=True,
)

restore_browser_session(conn)

if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False
if "admin_selected_candidate" not in st.session_state:
    st.session_state.admin_selected_candidate = None
if "admin_selected_role" not in st.session_state:
    st.session_state.admin_selected_role = ""

if not st.session_state.admin_logged_in:
    switch_page("login.py")
    st.stop()
else:
    st.markdown(
        """
<div class="brand-bar">
  <div class="brand-logo"><span class="brand-main">ABC</span><span class="brand-inc">INC</span></div>
  <div>
    <div class="brand-title">ABC INC ADMIN</div>
    <div class="brand-subtitle">Command Hub</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.title("Control Center")

    with st.sidebar:
        st.markdown("### Command Hub")
        st.markdown("#### 🎯 Smart Filters")
        st.markdown(
            """
<div class="sidebar-nav">
  <a class="sidebar-filter-btn" href="#overview">🧑 Profile Snapshot</a>
  <a class="sidebar-filter-btn" href="#scores">📊 Performance Metrics</a>
  <a class="sidebar-filter-btn" href="#suggestions">💡 Smart Insights</a>
  <a class="sidebar-filter-btn" href="#final-note">📝 Review Wrap-Up</a>
  <a class="sidebar-filter-btn" href="#analytics">📈 Insights Hub</a>
  <a class="sidebar-filter-btn" href="#comparison">🧩 Candidate Matchup</a>
  <a class="sidebar-filter-btn" href="#audit">🧾 Action Log</a>
</div>
""",
            unsafe_allow_html=True,
        )

        st.markdown("### Main Panels")
        panel_col_l1, panel_col_r1 = st.columns([0.82, 0.18])
        with panel_col_l1:
            st.markdown(
                '<div class="main-panel-label">📈 Insights Hub</div>',
                unsafe_allow_html=True,
            )
        with panel_col_r1:
            show_analytics = st.checkbox("Insights Hub", value=True, key="panel_analytics", label_visibility="collapsed")

        panel_col_l2, panel_col_r2 = st.columns([0.82, 0.18])
        with panel_col_l2:
            st.markdown(
                '<div class="main-panel-label">🧩 Candidate Matchup</div>',
                unsafe_allow_html=True,
            )
        with panel_col_r2:
            show_comparison = st.checkbox(
                "Candidate Matchup",
                value=True,
                key="panel_comparison",
                label_visibility="collapsed",
            )

        panel_col_l3, panel_col_r3 = st.columns([0.82, 0.18])
        with panel_col_l3:
            st.markdown(
                '<div class="main-panel-label">🧾 Action Log</div>',
                unsafe_allow_html=True,
            )
        with panel_col_r3:
            show_audit = st.checkbox("Action Log", value=True, key="panel_audit", label_visibility="collapsed")

    st.markdown("<div class='breadcrumbs'>Control Center &rsaquo; Talent Hub &rsaquo; Review</div>", unsafe_allow_html=True)
    top_left, top_right = st.columns([0.8, 0.2])
    with top_left:
        st.success("Welcome, Admin!")
    with top_right:
        if st.button("Logout"):
            clear_browser_session(conn)
            st.session_state.admin_logged_in = False
            st.session_state.admin_selected_candidate = None
            st.session_state.admin_selected_role = ""
            switch_page("login.py")

    with st.spinner("Loading dashboard data..."):
        df = get_dashboard_data()
    if df.empty:
        st.info("No candidate records found yet.")
    else:
        if "admin_quick_view" not in st.session_state:
            st.session_state.admin_quick_view = "all"

        with st.spinner("Preparing candidate insights..."):
            answer_index = build_answer_index(df["username"].tolist())
        latest_action_map = get_latest_admin_action_map(df["username"].tolist())
        widget_metrics = build_admin_widget_metrics(df, answer_index, latest_action_map)

        df = df.copy()
        df["latest_admin_action"] = df["username"].astype(str).map(lambda user: latest_action_map.get(str(user).strip(), ""))
        today = datetime.date.today()
        today_mask = df["profile_created_at"].apply(lambda value: _parse_date(value) == today)
        pending_mask = []
        for _, row in df.iterrows():
            username = str(row.get("username", "")).strip()
            answers = answer_index.get(username, [])
            review_needed = candidate_requires_review(answers, bool(int(row.get("is_banned", 0) or 0)))
            review_resolved = _is_review_resolved_action(row.get("latest_admin_action", ""))
            pending_mask.append(bool(review_needed and not review_resolved))
        df["pending_review"] = pending_mask

        pending_candidates_df = df.loc[df["pending_review"]].copy()
        today_candidates_df = df.loc[today_mask].copy()

        summary_col1, summary_col2, summary_col3 = st.columns(3)
        with summary_col1:
            st.metric("Total Candidates Today", widget_metrics["total_today"])
            if st.button("View Details", key="quick_view_today"):
                st.session_state.admin_quick_view = "today"
                st.rerun()
        with summary_col2:
            st.metric("Average Score", f"{widget_metrics['average_score']:.2f}/15")
            if st.session_state.get("admin_quick_view", "all") != "all":
                if st.button("Clear View", key="clear_quick_view"):
                    st.session_state.admin_quick_view = "all"
                    st.rerun()
        with summary_col3:
            st.metric("Pending Reviews", widget_metrics["pending_reviews"])
            if st.button("View Details", key="quick_view_pending"):
                st.session_state.admin_quick_view = "pending"
                st.rerun()

        quick_view = st.session_state.get("admin_quick_view", "all")
        if quick_view == "today":
            st.info("Quick View: showing only candidates added today.")
        elif quick_view == "pending":
            st.info("Quick View: showing only candidates with pending review.")

        st.markdown('<a id="today-candidates-quick-review"></a>', unsafe_allow_html=True)
        with st.expander("Total Candidates Today - Quick Review", expanded=False):
            if today_candidates_df.empty:
                st.info("No new candidates were registered today.")
            else:
                today_review_df = today_candidates_df[
                    [
                        "display_name",
                        "email",
                        "phone",
                        "applied_role",
                        "experience",
                        "previous_role",
                        "total_score_out_of_15",
                        "ban_status",
                    ]
                ].reset_index(drop=True)
                today_review_df.index = today_review_df.index + 1
                today_review_df.columns = [
                    "Name",
                    "Email",
                    "Phone",
                    "Applied Role",
                    "Experience",
                    "Previous Job Role",
                    "Interview Result",
                    "Status",
                ]
                st.dataframe(today_review_df, width="stretch")

        st.markdown('<a id="pending-reviews-quick-review"></a>', unsafe_allow_html=True)
        with st.expander("Pending Reviews - Quick Review", expanded=False):
            if pending_candidates_df.empty:
                st.success("No pending reviews right now.")
            else:
                pending_review_df = pending_candidates_df[
                    [
                        "display_name",
                        "email",
                        "phone",
                        "applied_role",
                        "experience",
                        "previous_role",
                        "total_score_out_of_15",
                        "ban_status",
                        "latest_admin_action",
                    ]
                ].reset_index(drop=True)
                pending_review_df.index = pending_review_df.index + 1
                pending_review_df.columns = [
                    "Name",
                    "Email",
                    "Phone",
                    "Applied Role",
                    "Experience",
                    "Previous Job Role",
                    "Interview Result",
                    "Status",
                    "Last Admin Action",
                ]
                st.dataframe(pending_review_df, width="stretch")

        auth_pending_df = df[df["interview_auth_status"].str.lower() == "pending"].copy()
        with st.container(border=True):
            st.subheader("Interview Authorization Requests")
            st.caption("Approve or reject candidates who requested to start their interview.")
            if auth_pending_df.empty:
                st.info("No pending interview authorization requests.")
            else:
                auth_pending_df["primary_skill"] = auth_pending_df["skills"].apply(lambda value: _split_skill_payload(value)[0])
                auth_pending_df["specializations"] = auth_pending_df["skills"].apply(lambda value: _split_skill_payload(value)[1])
                auth_table = auth_pending_df[
                    [
                        "display_name",
                        "email",
                        "phone",
                        "applied_role",
                        "experience",
                        "primary_skill",
                        "specializations",
                        "interview_auth_updated_at",
                    ]
                ].copy()
                auth_table = auth_table.rename(
                    columns={
                        "display_name": "Name",
                        "email": "Email",
                        "phone": "Phone",
                        "applied_role": "Applied Role",
                        "experience": "Experience",
                        "primary_skill": "Primary Skill",
                        "specializations": "Specializations",
                        "interview_auth_updated_at": "Requested At",
                    }
                )
                auth_table.index = auth_table.index + 1
                st.dataframe(auth_table, width="stretch")

                for _, row in auth_pending_df.iterrows():
                    name_text = str(row.get("display_name") or row.get("username") or "").strip()
                    email_text = str(row.get("email") or "").strip()
                    role_text = str(row.get("applied_role") or "").strip()
                    info_line = f"{name_text} | {email_text} | {role_text}"
                    col_info, col_confirm, col_reject = st.columns([0.6, 0.2, 0.2])
                    with col_info:
                        st.markdown(f"**{_escape_html(info_line)}**")
                    with col_confirm:
                        if st.button("Confirm", key=f"auth_confirm_{row['username']}"):
                            set_interview_auth_status(row["username"], "approved", actor="Admin")
                            st.success(f"Approved interview access for {name_text}.")
                            st.rerun()
                    with col_reject:
                        if st.button("Reject", key=f"auth_reject_{row['username']}"):
                            set_interview_auth_status(row["username"], "rejected", actor="Admin")
                            st.warning(f"Rejected interview access for {name_text}.")
                            st.rerun()

        st.markdown('<a id="overview"></a>', unsafe_allow_html=True)
        with st.container(border=True):
            st.subheader("Talent Hub")

            filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
            with filter_col1:
                search_text = st.text_input("Search Candidate", placeholder="Type name/email")
            with filter_col2:
                role_options = sorted([value for value in df["applied_role"].dropna().unique().tolist() if str(value).strip()])
                selected_roles = st.multiselect("Filter by Role", role_options)
            with filter_col3:
                score_min = int(df["total_score"].min()) if not df.empty else 0
                score_max = int(df["total_score"].max()) if not df.empty else 15
                if score_max < score_min:
                    score_max = score_min
                score_range = st.slider("Score Range", min_value=score_min, max_value=max(score_max, 1), value=(score_min, max(score_max, 1)))
            with filter_col4:
                status_filter = st.selectbox("Interview Status", ["All", "Active", "Banned"])

            if selected_roles:
                role_chips = "".join(
                    [f"<span class='keyword-chip'>{_escape_html(role)}</span>" for role in selected_roles]
                )
                st.markdown(
                    f"<div class='keyword-chip-row'><strong>Active role filters:</strong> {role_chips}</div>",
                    unsafe_allow_html=True,
                )

            filtered_df = df.copy()
            if search_text.strip():
                search_lower = search_text.strip().lower()
                filtered_df = filtered_df[
                    filtered_df["username"].astype(str).str.lower().str.contains(search_lower, na=False)
                    | filtered_df["display_name"].fillna("").astype(str).str.lower().str.contains(search_lower, na=False)
                    | filtered_df["email"].fillna("").astype(str).str.lower().str.contains(search_lower, na=False)
                ]
            if selected_roles:
                filtered_df = filtered_df[filtered_df["applied_role"].isin(selected_roles)]
            filtered_df = filtered_df[
                (filtered_df["total_score"] >= score_range[0]) &
                (filtered_df["total_score"] <= score_range[1])
            ]
            if status_filter != "All":
                filtered_df = filtered_df[filtered_df["ban_status"].str.contains(status_filter, case=False, na=False)]

            quick_view = st.session_state.get("admin_quick_view", "all")
            if quick_view == "today":
                filtered_df = filtered_df[
                    filtered_df["profile_created_at"].apply(lambda value: _parse_date(value) == today)
                ]
            elif quick_view == "pending":
                filtered_df = filtered_df[filtered_df["pending_review"]]

            summary_table_df = filtered_df[
                [
                    "display_name",
                    "email",
                    "phone",
                    "experience",
                    "previous_role",
                    "applied_role",
                    "ban_status",
                    "ban_reason",
                    "correct_normal",
                    "partial_normal",
                    "incorrect_normal",
                    "correct_hard",
                    "partial_hard",
                    "incorrect_hard",
                    "total_score_out_of_15",
                ]
            ].reset_index(drop=True)
            summary_table_df = summary_table_df.rename(columns={"display_name": "Name"})
            summary_table_df.index = summary_table_df.index + 1
            st.dataframe(summary_table_df, width="stretch")

        with st.container(border=True):
            st.subheader("Profile Manager")
            candidate_options = filtered_df["username"].tolist()
            if not candidate_options:
                st.info("No candidates match the current filter selection.")
            else:
                name_lookup = filtered_df.set_index("username")["display_name"].to_dict()
                email_lookup = filtered_df.set_index("username")["email"].to_dict()
                selected_index = 0
                if st.session_state.admin_selected_candidate in candidate_options:
                    selected_index = candidate_options.index(st.session_state.admin_selected_candidate)
                selected_candidate = st.selectbox(
                    "Candidate",
                    candidate_options,
                    index=selected_index,
                    format_func=lambda user_key: f"{name_lookup.get(user_key, user_key)} ({email_lookup.get(user_key, user_key)})",
                )
                if st.button("Open Answers and See Insights"):
                    st.session_state.admin_selected_candidate = selected_candidate
                    role_match = filtered_df.loc[filtered_df["username"] == selected_candidate, "applied_role"]
                    st.session_state.admin_selected_role = role_match.iloc[0] if not role_match.empty else ""

                st.caption("Candidate dashboard can be opened from the main login app entrypoint.")

                if st.session_state.admin_selected_candidate in candidate_options:
                    show_answers_and_insights(st.session_state.admin_selected_candidate)

        if show_analytics:
            with st.container(border=True):
                st.markdown('<a id="analytics"></a>', unsafe_allow_html=True)
                st.subheader("Analysis")
                role_trend_df = build_role_trend_dataset(filtered_df)
                hard_success_df = build_hard_success_dataset(filtered_df)

                vis_col1, vis_col2 = st.columns(2)
                with vis_col1:
                    st.markdown("**Average Score by Role**")
                    if role_trend_df.empty:
                        st.info("No role trend data available.")
                    else:
                        render_fixed_bar_chart(
                            role_trend_df,
                            "Role",
                            "Average Score",
                            "Average Score",
                            title="",
                            color="#0b4db6",
                        )
                with vis_col2:
                    st.markdown("**Hard Question Success Rate by Role**")
                    if hard_success_df.empty:
                        st.info("No hard-question trend data available.")
                    else:
                        render_fixed_line_chart(
                            hard_success_df,
                            "Role",
                            ["Hard Success Rate"],
                            title="",
                            color_scale={"domain": ["Hard Success Rate"], "range": ["#2e7d32"]},
                        )

                st.markdown("**Overall Result Distribution**")
                pie_data = pd.DataFrame(
                    [
                        {"Result": "Correct", "Count": int(filtered_df["correct_normal"].fillna(0).sum() + filtered_df["correct_hard"].fillna(0).sum())},
                        {"Result": "Partially Correct", "Count": int(filtered_df["partial_normal"].fillna(0).sum() + filtered_df["partial_hard"].fillna(0).sum())},
                        {"Result": "Incorrect", "Count": int(filtered_df["incorrect_normal"].fillna(0).sum() + filtered_df["incorrect_hard"].fillna(0).sum())},
                    ]
                )
                render_fixed_pie_chart(
                    pie_data,
                    "Result",
                    "Count",
                    title="",
                    color_scale={
                        "domain": ["Correct", "Partially Correct", "Incorrect"],
                        "range": ["#2e7d32", "#0b4db6", "#c62828"],
                    },
                )

        if show_comparison:
            with st.container(border=True):
                st.markdown('<a id="comparison"></a>', unsafe_allow_html=True)
                st.subheader("Candidate Matchup")
                role_options = sorted([value for value in filtered_df["applied_role"].dropna().unique().tolist() if str(value).strip()])
                if not role_options:
                    st.info("Candidate matchup becomes available once candidates exist for a role.")
                else:
                    comparison_role = st.selectbox("Compare Role", role_options, key="compare_role")
                    role_candidates = filtered_df.loc[filtered_df["applied_role"] == comparison_role, "username"].tolist()
                    if len(role_candidates) < 2:
                        st.info("At least two candidates are needed for side-by-side comparison.")
                    else:
                        name_lookup = filtered_df.set_index("username")["display_name"].to_dict()
                        email_lookup = filtered_df.set_index("username")["email"].to_dict()
                        format_candidate = lambda user_key: f"{name_lookup.get(user_key, user_key)} ({email_lookup.get(user_key, user_key)})"
                        comp_col1, comp_col2 = st.columns(2)
                        with comp_col1:
                            candidate_a = st.selectbox(
                                "Candidate A",
                                role_candidates,
                                key="compare_candidate_a",
                                format_func=format_candidate,
                            )
                        with comp_col2:
                            candidate_b = st.selectbox(
                                "Candidate B",
                                role_candidates,
                                key="compare_candidate_b",
                                index=1 if len(role_candidates) > 1 else 0,
                                format_func=format_candidate,
                            )

                        row_a = filtered_df.loc[filtered_df["username"] == candidate_a].iloc[0]
                        row_b = filtered_df.loc[filtered_df["username"] == candidate_b].iloc[0]
                        candidate_a_label = format_candidate(candidate_a)
                        candidate_b_label = format_candidate(candidate_b)
                        card_a = build_candidate_comparison_card(candidate_a, row_a["total_score"], answer_index.get(candidate_a, []))
                        card_b = build_candidate_comparison_card(candidate_b, row_b["total_score"], answer_index.get(candidate_b, []))

                        summary_a, summary_b = st.columns(2)
                        with summary_a:
                            st.markdown(
                                f"""
<div class="compare-card">
  <div class="compare-card-label">Candidate A</div>
  <div class="compare-card-value">{_escape_html(str(candidate_a_label))} | Score {int(_safe_float(card_a.get('Score'), 0))}/15</div>
</div>
""",
                                unsafe_allow_html=True,
                            )
                        with summary_b:
                            st.markdown(
                                f"""
<div class="compare-card">
  <div class="compare-card-label">Candidate B</div>
  <div class="compare-card-value">{_escape_html(str(candidate_b_label))} | Score {int(_safe_float(card_b.get('Score'), 0))}/15</div>
</div>
""",
                                unsafe_allow_html=True,
                            )

                        compare_df = pd.DataFrame([card_a, card_b])
                        compare_df["Candidate"] = [candidate_a_label, candidate_b_label]
                        compare_df.index = compare_df.index + 1
                        st.dataframe(compare_df, width="stretch")
                        render_fixed_line_chart(
                            compare_df,
                            "Candidate",
                            ["Score", "Avg Relevance", "Avg Confidence"],
                            "Side-by-Side Candidate Comparison",
                            width=860,
                            height=320,
                            color_scale={
                                "domain": ["Score", "Avg Relevance", "Avg Confidence"],
                                "range": ["#0b4db6", "#2e7d32", "#18a999"],
                            },
                            y_title="Score / Percentage",
                        )

        if show_audit:
            with st.container(border=True):
                st.markdown('<a id="audit"></a>', unsafe_allow_html=True)
                st.subheader("Action Log")
                audit_df = get_audit_trail(limit=150)
                if audit_df.empty:
                    st.info("No audit entries yet.")
                else:
                    audit_display_df = audit_df.copy().reset_index(drop=True)
                    audit_display_df.index = audit_display_df.index + 1
                    audit_display_df.columns = ["Username", "Action", "Reason", "Actor", "Timestamp"]
                    styled_audit = (
                        audit_display_df.style
                        .apply(_audit_row_style, axis=1)
                        .set_table_styles(
                            [
                                {"selector": "th", "props": "background-color: #dbeafe; color: #0f172a; font-weight: 700;"},
                                {"selector": "th.row_heading", "props": "background-color: #dbeafe; color: #0f172a; font-weight: 700;"},
                            ],
                            overwrite=False,
                        )
                    )
                    st.dataframe(styled_audit, width="stretch")

save_browser_session(conn)
