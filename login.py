import base64
import json
import datetime
import re
import sqlite3
import html
from pathlib import Path
import streamlit as st
from werkzeug.security import check_password_hash, generate_password_hash

# Database setup
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
    """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    confirm_password_hash TEXT NOT NULL)""")
conn.commit()
# Candidate profile and interview results tables
cursor.execute("""
CREATE TABLE IF NOT EXISTS candidate_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    role TEXT NOT NULL,
    experience TEXT NOT NULL,
    experience_years INTEGER,
    previous_role TEXT,
    skills TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(username) REFERENCES users(username)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS interview_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    role TEXT NOT NULL,
    experience TEXT NOT NULL,
    correct_normal INTEGER,
    partial_normal INTEGER,
    incorrect_normal INTEGER,
    correct_hard INTEGER,
    partial_hard INTEGER,
    incorrect_hard INTEGER,
    original_answers TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(username) REFERENCES users(username)
)
""")
conn.commit()


def ensure_schema():
    cursor.execute("PRAGMA table_info(users)")
    columns = {row[1] for row in cursor.fetchall()}
    if "confirm_password_hash" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN confirm_password_hash TEXT NOT NULL DEFAULT ''")
    cursor.execute("PRAGMA table_info(candidate_profiles)")
    profile_columns = {row[1] for row in cursor.fetchall()}
    if "phone" not in profile_columns:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN phone TEXT")
    if "email" not in profile_columns:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN email TEXT")
    if "experience_years" not in profile_columns:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN experience_years INTEGER")
    if "previous_role" not in profile_columns:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN previous_role TEXT")
    if "is_banned" not in profile_columns:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0")
    if "ban_until" not in profile_columns:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN ban_until TEXT")
    if "ban_reason" not in profile_columns:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN ban_reason TEXT")
    if "created_at" not in profile_columns:
        cursor.execute("ALTER TABLE candidate_profiles ADD COLUMN created_at TEXT")
    cursor.execute("UPDATE candidate_profiles SET created_at = datetime('now') WHERE created_at IS NULL OR created_at = ''")
    cursor.execute("PRAGMA table_info(interview_results)")
    result_columns = {row[1] for row in cursor.fetchall()}
    if "original_answers" not in result_columns:
        cursor.execute("ALTER TABLE interview_results ADD COLUMN original_answers TEXT")
    if "created_at" not in result_columns:
        cursor.execute("ALTER TABLE interview_results ADD COLUMN created_at TEXT")
    cursor.execute("UPDATE interview_results SET created_at = datetime('now') WHERE created_at IS NULL OR created_at = ''")
    conn.commit()
ensure_schema()


# Helper functions
def validate_password(password):
    rules = []
    if len(password) < 8:
        rules.append("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", password):
        rules.append("Password must include at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        rules.append("Password must include at least one lowercase letter.")
    if not re.search(r"\d", password):
        rules.append("Password must include at least one number.")
    if not re.search(r"[^\w\s]", password):
        rules.append("Password must include at least one special character.")
    if re.search(r"\s", password):
        rules.append("Password must not contain spaces.")
    return rules

def validate_email(email):
    return re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email) is not None

def validate_phone(phone):
    digit_count = sum(char.isdigit() for char in phone)
    return 10 <= digit_count <= 15

def register_user(username, password, confirm_password):
    try:
        password_hash = generate_password_hash(password)
        confirm_hash = generate_password_hash(confirm_password)
        cursor.execute(
            "INSERT INTO users (username, password_hash, confirm_password_hash) VALUES (?, ?, ?)",
            (username, password_hash, confirm_hash),
        )
        conn.commit()
        return True, "Registration successful. You can now log in."
    except sqlite3.IntegrityError:
        return False, "Username already exists. Please choose another."

def login_user(username, password):
    cursor.execute("SELECT password_hash FROM users WHERE username=?", (username,))
    result = cursor.fetchone()
    if result:
        stored_hash = result[0]
        if check_password_hash(stored_hash, password):
            return True, "Login successful."
        else:
            return False, "Incorrect password. Please try again."
    else:
        return False, "Username not found. Please register first."

def save_candidate_profile(
    username,
    phone,
    email,
    role,
    experience,
    skills,
    experience_years=None,
    previous_role=None,
):
    created_at = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO candidate_profiles
        (username, phone, email, role, experience, experience_years, previous_role, skills, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (username, phone, email, role, experience, experience_years, previous_role, ",".join(skills), created_at)
    )
    conn.commit()

def parse_original_answers(raw_value):
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]

def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


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


def _escape_html(value):
    return html.escape(str(value or ""), quote=True)


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


def _clamp_percentage(value):
    try:
        return max(0.0, min(float(value), 100.0))
    except (TypeError, ValueError):
        return 0.0


def render_score_meter(label, value, tone="brand"):
    tone_colors = {
        "brand": "#0b4db6",
        "success": "#157a39",
        "warning": "#d9822b",
        "neutral": "#5f6b7a",
    }
    score = _clamp_percentage(value)
    color = tone_colors.get(tone, tone_colors["brand"])
    st.markdown(
        f"""
<div class="score-meter">
  <div class="score-meter-header">
    <span>{_escape_html(label)}</span>
    <span>{score:.1f}%</span>
  </div>
  <div class="score-meter-track">
    <div class="score-meter-fill" style="width: {score:.1f}%; background: {color};"></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def build_guided_improvement_plan(topic, missing_keywords, improvement_hints, result_label):
    topic_label = str(topic or "the concept").strip() or "the concept"
    missing_text = ", ".join(missing_keywords[:3]) if missing_keywords else "the key terms asked in the question"

    positive_intro = "Great start!"
    if str(result_label or "").strip().lower() == "correct":
        positive_intro = "Strong base!"

    hint_text = ""
    if isinstance(improvement_hints, list):
        cleaned_hints = [str(item).strip() for item in improvement_hints if str(item).strip()]
        if cleaned_hints:
            hint_text = cleaned_hints[0]

    definition_line = f"{positive_intro} Define {topic_label.lower()} in one crisp sentence before details."
    mechanism_line = f"Explain how it works step-by-step and explicitly mention {missing_text}."
    practical_line = "Close with one real-world use case and the measurable outcome (speed, quality, or cost)."

    if hint_text:
        practical_line = f"{practical_line} Extra focus: {hint_text}"

    return [definition_line, mechanism_line, practical_line]


def get_active_ban_status(username):
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


def render_answer_level_insights(answer_rows):
    if not answer_rows:
        return

    st.markdown(
        """
<a id="answer-insights"></a>
<div class="section-anchor-title">Answer-by-Answer Insights</div>
""",
        unsafe_allow_html=True,
    )
    fallback_map = {
        "Correct": (85.0, 75.0),
        "Partially Correct": (55.0, 60.0),
        "Incorrect": (25.0, 50.0),
    }

    for row in answer_rows:
        question_no = row.get("question_no", "")
        question_text = row.get("question_text", "")
        answer_text = row.get("answer_text", "")
        result_label = row.get("result_label", "")
        difficulty = str(row.get("difficulty", "")).strip() or "N/A"
        topic = str(row.get("topic") or "General").strip() or "General"
        relevance = _safe_float(row.get("relevance_score"), 0.0)
        confidence = _safe_float(row.get("confidence_score"), 0.0)
        if relevance == 0.0 and confidence == 0.0 and result_label in fallback_map:
            relevance, confidence = fallback_map[result_label]

        improvements = row.get("improvement_insights", [])
        if not isinstance(improvements, list):
            improvements = []
        improvements = [str(item).strip() for item in improvements if str(item).strip()]
        matched_keywords = _normalize_keywords(row.get("matched_keywords", []))
        missing_keywords = _normalize_keywords(row.get("missing_keywords", []))
        guided_plan = build_guided_improvement_plan(topic, missing_keywords, improvements, result_label)

        expander_label = f"Q{question_no}. {question_text}"
        with st.expander(expander_label, expanded=False):
            st.write(f"Your Answer: {answer_text if answer_text else '(No answer provided)'}")
            result_line = _escape_html(f"{result_label} | Difficulty: {difficulty}")
            relevance_line = _escape_html(f"{relevance:.1f}% | Confidence: {confidence:.1f}%")
            matched_line = _escape_html(", ".join(matched_keywords) if matched_keywords else "None")
            missed_line = _escape_html(", ".join(missing_keywords) if missing_keywords else "None")

            st.markdown(
                f"""
<div style="font-size: 15px; line-height: 1.5; color: var(--text-primary); margin-top: 0.35rem;">
  <div style="font-weight: 600;">🧾 Result: {result_line}</div>
  <div style="font-weight: 600; margin-top: 0.2rem;">📊 Relevance: {relevance_line}</div>
  <div style="font-weight: 600; margin-top: 0.2rem;">✅ Matched Keywords: {matched_line}</div>
  <div style="font-weight: 600; margin-top: 0.2rem;">🧩 Missed Keywords: {missed_line}</div>
</div>
""",
                unsafe_allow_html=True,
            )

            st.write("")
            st.markdown("Guided Improvement Plan")
            st.write(f"✅ Definition: {guided_plan[0]}")
            st.write(f"⚙️ Mechanism: {guided_plan[1]}")
            st.write(f"📈 Practical Impact: {guided_plan[2]}")

            if improvements:
                st.caption("Additional hints:")
                for suggestion in improvements[:2]:
                    st.write(f"- {suggestion}")

def build_feedback_summary(answer_rows):
    if not answer_rows:
        return None

    fallback_map = {
        "Correct": (85.0, 75.0),
        "Partially Correct": (55.0, 60.0),
        "Incorrect": (25.0, 50.0),
    }

    topic_stats = {}
    total_relevance = 0.0
    total_confidence = 0.0
    hard_relevance_total = 0.0
    hard_count = 0

    for row in answer_rows:
        topic = str(row.get("topic") or "General").strip() or "General"
        result_label = row.get("result_label", "")

        relevance = _safe_float(row.get("relevance_score"), 0.0)
        confidence = _safe_float(row.get("confidence_score"), 0.0)

        if relevance == 0.0 and confidence == 0.0 and result_label in fallback_map:
            relevance, confidence = fallback_map[result_label]

        difficulty = str(row.get("difficulty", "")).strip().lower()
        missing_keywords = [
            kw.strip().lower()
            for kw in row.get("missing_keywords", [])
            if isinstance(kw, str) and kw.strip()
        ]

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

        sorted_missing = sorted(stats["missing"].items(), key=lambda item: (-item[1], item[0]))
        top_missing = [keyword for keyword, _ in sorted_missing[:3]]

        topic_analysis.append(
            {
                "Topic": topic,
                "Questions": stats["count"],
                "Avg Relevance (%)": round(avg_relevance, 1),
                "Avg Confidence (%)": round(avg_confidence, 1),
                "Top Missing Keywords": ", ".join(top_missing) if top_missing else "-",
            }
        )

        if avg_relevance >= 70 and avg_confidence >= 60:
            strengths.append(
                f"{topic}: strong answers with {avg_relevance:.1f}% relevance and {avg_confidence:.1f}% confidence."
            )

        if avg_relevance < 60:
            if top_missing:
                improvements.append(f"{topic}: great start. Consider adding {', '.join(top_missing)} to make answers stronger.")
            else:
                improvements.append(f"{topic}: great effort. Consider adding more depth and clearer structure.")

    topic_analysis.sort(key=lambda item: item["Avg Relevance (%)"], reverse=True)

    if not strengths:
        if topic_analysis:
            strongest_topic = topic_analysis[0]["Topic"]
            strengths.append(
                f"{strongest_topic}: comparatively better performance; keep building structured explanations."
            )
        else:
            strengths.append("You attempted the interview and have a base to improve from.")

    if not improvements:
        improvements.append("Great consistency so far. Consider adding one deeper hard-question example to reach the next level.")

    avg_relevance = total_relevance / len(answer_rows)
    avg_confidence = total_confidence / len(answer_rows)
    hard_avg_relevance = (hard_relevance_total / hard_count) if hard_count else None

    top_missing_keywords = []
    for row in topic_analysis:
        raw_keywords = row["Top Missing Keywords"]
        if raw_keywords and raw_keywords != "-":
            for kw in [item.strip() for item in raw_keywords.split(",") if item.strip()]:
                if kw not in top_missing_keywords:
                    top_missing_keywords.append(kw)

    return {
        "avg_relevance": round(avg_relevance, 1),
        "avg_confidence": round(avg_confidence, 1),
        "hard_avg_relevance": round(hard_avg_relevance, 1) if hard_avg_relevance is not None else None,
        "strengths": strengths[:3],
        "improvements": improvements[:3],
        "topic_analysis": topic_analysis,
        "top_missing_keywords": top_missing_keywords[:5],
    }


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
    rows = cursor.execute(
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


def get_interview_result_by_id(username, interview_id=None):
    if interview_id is None:
        query = """
            SELECT id, role, experience, correct_normal, partial_normal, correct_hard, partial_hard, original_answers, created_at
            FROM interview_results
            WHERE username = ?
            ORDER BY id DESC
            LIMIT 1
        """
        params = (username,)
    else:
        query = """
            SELECT id, role, experience, correct_normal, partial_normal, correct_hard, partial_hard, original_answers, created_at
            FROM interview_results
            WHERE username = ? AND id = ?
            LIMIT 1
        """
        params = (username, int(interview_id))

    row = cursor.execute(query, params).fetchone()
    if not row:
        return None

    score = int(
        _safe_float(row[3], 0.0)
        + _safe_float(row[4], 0.0)
        + _safe_float(row[5], 0.0)
        + _safe_float(row[6], 0.0)
    )
    original_answers = parse_original_answers(row[7])

    return {
        "id": int(_safe_float(row[0], 0.0)),
        "role": str(row[1] or "").strip(),
        "experience": str(row[2] or "").strip(),
        "score": score,
        "created_at": row[8],
        "feedback": build_feedback_summary(original_answers),
        "original_answers": original_answers,
    }


def get_latest_interview_result(username):
    return get_interview_result_by_id(username)


def get_latest_candidate_profile(username):
    cursor.execute(
        """
        SELECT phone, email, role, experience, previous_role, skills
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

    raw_skills = row[5] or ""
    parsed_skills = [skill.strip() for skill in raw_skills.split(",") if skill.strip()]

    return {
        "phone": row[0],
        "email": row[1],
        "role": row[2],
        "experience": row[3],
        "previous_role": row[4],
        "skills": parsed_skills,
    }


def build_role_performance_suggestion(avg_score, avg_relevance, avg_confidence, improvement_hint):
    if avg_score >= 11 and avg_relevance >= 75 and avg_confidence >= 65:
        base = "Strong consistency. Focus on advanced scenarios and production trade-offs."
    elif avg_score >= 8:
        base = "Good momentum. Improve depth and structure to push into top-tier performance."
    else:
        base = "Strengthen fundamentals with clearer definitions, mechanisms, and practical examples."

    hint = str(improvement_hint or "").strip()
    if hint:
        return f"{base} Priority: {hint}"
    return base


def get_candidate_multi_interview_insights(username):
    rows = cursor.execute(
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
        answer_rows = parse_original_answers(row[5])

        bucket = role_aggregate.setdefault(
            role_name,
            {"attempts": 0, "score_total": 0.0, "answer_rows": []},
        )
        bucket["attempts"] += 1
        bucket["score_total"] += interview_score
        bucket["answer_rows"].extend(answer_rows)

    ordered_roles = ["Developer", "Tester", "Analyst"]
    sort_index = {name: index for index, name in enumerate(ordered_roles)}
    role_insights = []
    attempted_roles = sorted(role_aggregate.keys(), key=lambda name: sort_index.get(name, 999))

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


def update_candidate_skills(username, skills):
    cursor.execute(
        """
        UPDATE candidate_profiles
        SET skills = ?
        WHERE id = (
            SELECT id
            FROM candidate_profiles
            WHERE username = ?
            ORDER BY id DESC
            LIMIT 1
        )
        """,
        (
            ",".join(skills),
            username,
        ),
    )
    conn.commit()


def get_role_skill_map(role):
    return {
        "Developer": {
            "Python": [
                "Django",
                "Flask",
                "FastAPI",
                "Data Science",
                "Machine Learning",
                "Deep Learning",
                "Async Python",
                "Automation Scripting",
                "REST APIs with Python",
                "Web Scraping",
            ],
            "HTML/CSS": [
                "Responsive Design",
                "Bootstrap",
                "Tailwind CSS",
                "CSS Flexbox/Grid",
                "UI Components",
                "SASS/SCSS",
                "CSS Animations",
                "Accessibility (a11y)",
                "Design Systems",
            ],
            "Java": [
                "Spring Boot",
                "Hibernate",
                "REST APIs",
                "Microservices",
                "Multithreading",
                "Spring Security",
                "JUnit",
                "JPA",
                "Kafka Integration",
            ],
        },
        "Tester": {
            "Manual Testing": [
                "Test Case Design",
                "Smoke Testing",
                "Regression Testing",
                "UAT",
                "Defect Tracking",
                "Test Planning",
                "Boundary Value Analysis",
                "Compatibility Testing",
                "Bug Lifecycle",
            ],
            "Automation Testing": [
                "Selenium",
                "Cypress",
                "Playwright",
                "TestNG",
                "Pytest",
                "BDD (Cucumber)",
                "Page Object Model",
                "CI Integration",
                "API Automation",
            ],
            "API Testing": [
                "Postman",
                "REST Assured",
                "Authentication Testing",
                "Contract Testing",
                "Performance Basics",
                "Swagger/OpenAPI",
                "Load Testing",
                "Mock Services",
                "OAuth/JWT Validation",
            ],
        },
        "Analyst": {
            "Data Analysis": [
                "Data Cleaning",
                "Exploratory Analysis",
                "Statistical Analysis",
                "Advanced Excel",
                "Python Pandas",
                "SQL for Analysis",
                "A/B Testing",
                "Forecasting",
                "Data Visualization Basics",
            ],
            "Business Intelligence": [
                "Power BI",
                "Tableau",
                "Dashboard Design",
                "KPI Reporting",
                "Data Storytelling",
                "DAX",
                "Data Modeling",
                "ETL Concepts",
                "Drill-through Reports",
            ],
            "Business Analysis": [
                "Requirements Gathering",
                "Process Modeling",
                "Stakeholder Management",
                "BRD/FRD",
                "Gap Analysis",
                "User Stories",
                "Wireframing",
                "Risk Analysis",
                "Agile/Scrum",
            ],
        },
    }.get(role, {})


def build_selected_skill_payload(primary_skills, specialization_map):
    payload = []
    for primary in primary_skills:
        payload.append(primary)
        for specialization in specialization_map.get(primary, []):
            payload.append(f"{primary} - {specialization}")
    return payload


def reset_interview_session_state():
    fixed_keys = (
        "role",
        "experience",
        "selected_primary_skill",
        "selected_specializations",
        "dashboard_active_skill",
        "interview_questions",
        "interview_questions_meta",
        "answer_audio_blobs",
        "current_index",
        "answers",
        "answer_drafts",
        "interview_submitted",
        "results_summary",
        "results_saved",
        "policy_violation_summary",
        "allow_retest",
        "show_answer_review",
    )

    for key in fixed_keys:
        if key in st.session_state:
            del st.session_state[key]

    dynamic_prefixes = ("ans_", "recorded_audio_", "processed_audio_digest_")
    dynamic_keys = [key for key in list(st.session_state.keys()) if key.startswith(dynamic_prefixes)]
    for key in dynamic_keys:
        del st.session_state[key]
# Streamlit UI
st.set_page_config(page_title="ABC Inc", layout="wide", initial_sidebar_state="collapsed")
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Roboto:wght@500;700&display=swap');

[data-testid="stSidebarNav"] {
  display: none;
}

:root {
  --brand-primary: #0b4db6;
  --brand-primary-strong: #083a89;
  --brand-accent: #18a999;
  --text-primary: #12223a;
  --text-secondary: #334f72;
  --card-bg: #ffffff;
  --card-border: #dfe8f5;
  --shadow-soft: 0 10px 26px rgba(12, 45, 95, 0.12);
}

html[data-theme="dark"] {
  --text-primary: #e8eefb;
  --text-secondary: #cedcf3;
  --card-bg: #13233b;
  --card-border: #3d5273;
}

html, body, [class*="css"] {
  font-family: "Inter", "Roboto", Arial, sans-serif;
  color: var(--text-primary);
}

h1, h2, h3, h4 {
  font-family: "Roboto", "Inter", Arial, sans-serif;
  letter-spacing: 0.01em;
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
  padding: 16px 20px;
  border-radius: 16px;
  color: #ffffff;
  margin-bottom: 18px;
  box-shadow: var(--shadow-soft);
  display: flex;
  align-items: center;
  gap: 14px;
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

.section-card {
  background: linear-gradient(135deg, rgba(13, 44, 86, 0.74) 0%, rgba(21, 64, 118, 0.68) 100%);
  padding: 18px 20px;
  border-radius: 14px;
  border: 1px solid rgba(173, 199, 235, 0.5);
  box-shadow: 0 12px 26px rgba(13, 44, 86, 0.22);
  margin-bottom: 14px;
  color: #f4f8ff;
  backdrop-filter: blur(6px);
}

.section-card strong {
  color: #ffffff;
}

.summary-card {
  background: linear-gradient(115deg, #083a89 0%, #0b4db6 45%, #1a6fd1 100%);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #ffffff;
  padding: 18px 20px;
  box-shadow: var(--shadow-soft);
  margin-bottom: 14px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.summary-item {
  background: rgba(255, 255, 255, 0.16);
  border-radius: 10px;
  padding: 10px;
}

.summary-label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  opacity: 0.9;
}

.summary-value {
  font-size: 17px;
  font-weight: 700;
  margin-top: 2px;
}

.status-pill {
  display: inline-block;
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.status-pill.active {
  color: #145d2e;
  background: #e6f7eb;
}

.status-pill.banned {
  color: #8a1e1e;
  background: #fdeaea;
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

.section-anchor-title {
  font-family: "Roboto", Arial, sans-serif;
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 8px 0 12px;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 8px 0 6px 0;
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

.score-meter {
  margin-bottom: 10px;
}

.score-meter-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.score-meter-track {
  height: 10px;
  width: 100%;
  border-radius: 999px;
  background: #ebf1fb;
  overflow: hidden;
}

.score-meter-fill {
  height: 100%;
  border-radius: 999px;
  transform-origin: left center;
  animation: meterGrow 0.7s ease;
}

.keyword-chip-row {
  margin-top: 8px;
  margin-bottom: 10px;
}

.keyword-chip {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 999px;
  font-size: 12px;
  margin: 4px 6px 0 0;
  border: 1px solid transparent;
}

.keyword-chip.warning {
  background: #fff3e2;
  color: #915100;
  border-color: #f4cc98;
}

.keyword-chip.success {
  background: #e8f7ed;
  color: #146332;
  border-color: #b8e5c4;
}

.guidance-note {
  color: #21558f;
  font-size: 13px;
  margin-top: 6px;
}

.stButton > button {
  background: var(--brand-primary);
  color: #ffffff;
  border: 0;
  padding: 0.56rem 1.2rem;
  border-radius: 10px;
  font-weight: 600;
}

.stButton > button {
  transition: transform 0.16s ease, box-shadow 0.16s ease, background-color 0.16s ease;
}

.stButton > button:hover {
  background: var(--brand-primary-strong);
  transform: translateY(-1px);
  box-shadow: 0 6px 14px rgba(11, 77, 182, 0.24);
}

.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stSelectbox > div > div > div,
.stMultiSelect > div > div > div {
  border-radius: 10px;
}

div[data-testid="stTabs"] button {
  font-weight: 600;
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

.form-hint {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 8px;
}

.promo-card {
  background: linear-gradient(132deg, #0f7a6d 0%, #16a395 100%);
  color: #ffffff;
  padding: 24px;
  border-radius: 14px;
  box-shadow: 0 14px 26px rgba(15, 122, 109, 0.28);
}

.promo-title {
  font-family: "Roboto", Arial, sans-serif;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-weight: 700;
  font-size: 18px;
}

.promo-highlight {
  font-size: 18px;
  font-weight: 600;
  margin-top: 14px;
}

.promo-copy {
  font-size: 14px;
  line-height: 1.55;
  margin-top: 16px;
  opacity: 0.95;
}

.promo-badge {
  display: inline-block;
  margin-top: 18px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.18);
  font-size: 12px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.skill-box-title {
  padding: 14px 16px;
  border-radius: 12px;
  text-align: center;
  font-family: "Roboto", Arial, sans-serif;
  font-weight: 700;
  font-size: 17px;
  margin-bottom: 12px;
  letter-spacing: 0.02em;
}

.skill-box-active {
  background: linear-gradient(135deg, #0b4db6 0%, #2d78e6 100%);
  color: #ffffff;
  box-shadow: 0 10px 22px rgba(11, 77, 182, 0.24);
}

.skill-box-inactive {
  background: linear-gradient(180deg, #f7fbff 0%, #ebf2ff 100%);
  color: #114496;
}

.skill-box-subtitle {
  margin-top: 8px;
  margin-bottom: 6px;
  color: #294a84;
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.specialization-count {
  margin-top: 10px;
  display: inline-block;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.specialization-count.ok {
  background: #e4f8ea;
  color: #156c2f;
}

.specialization-count.warn {
  background: #fff3dc;
  color: #8a5a00;
}

@keyframes meterGrow {
  from { transform: scaleX(0); }
  to { transform: scaleX(1); }
}

@media (max-width: 960px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .brand-bar {
    padding: 14px 16px;
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

st.markdown(
    """
<div class="brand-bar">
  <div class="brand-logo"><span class="brand-main">ABC</span><span class="brand-inc">INC</span></div>
  <div>
    <div class="brand-title">ABC INC<sup>&reg;</sup></div>
    <div class="brand-subtitle">Global Talent Acquisition | Interview Portal</div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)


# Session state for authentication
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = None
if "auth_view" not in st.session_state:
    st.session_state.auth_view = "login"

registration_success_message = st.session_state.pop("registration_success_message", None)

if not st.session_state.logged_in:
    login_wallpaper_uri = _file_data_uri(r"D:\Interview bot\pexels-jplenio-1103970.jpg")
    if not login_wallpaper_uri:
        login_wallpaper_uri = _file_data_uri("pexels-jplenio-1103970.jpg")

    if login_wallpaper_uri:
        login_background_css = (
            "background: linear-gradient(135deg, rgba(18, 40, 70, 0.34) 0%, rgba(23, 52, 86, 0.38) 55%, "
            f"rgba(19, 43, 73, 0.42) 100%), url('{login_wallpaper_uri}') center center / cover no-repeat !important;"
        )
    else:
        login_background_css = (
            "background: radial-gradient(circle at 18% 12%, rgba(140, 184, 245, 0.58) 0%, rgba(140, 184, 245, 0) 44%), "
            "radial-gradient(circle at 84% 18%, rgba(114, 189, 212, 0.32) 0%, rgba(114, 189, 212, 0) 38%), "
            "linear-gradient(180deg, #eef4ff 0%, #deebfb 52%, #d2e0f4 100%) !important;"
        )

    st.markdown(
        """
<style>
[data-testid="stAppViewContainer"] {
  __LOGIN_BG__
}
[data-testid="stAppViewContainer"] .main {
  background: transparent !important;
}
.brand-bar {
  max-width: 560px;
  margin: 0 auto 18px auto !important;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 10px;
}
.brand-title {
  letter-spacing: 0.12em;
}
.brand-subtitle {
  margin-top: 4px;
}
.section-card {
  max-width: 560px;
  margin: 0 auto 14px auto !important;
  text-align: center;
}
</style>
""".replace("__LOGIN_BG__", login_background_css),
        unsafe_allow_html=True,
    )

promo_card_html = """
<div class="promo-card">
  <div class="promo-title">Join Us</div>
  <div class="promo-highlight">Make your career sky rocketing.</div>
  <div class="promo-copy">
    Work with global teams, build products used by millions, and grow faster than you thought possible.
    Elite mentorship, top-tier tools, and a brand trusted worldwide.
    Your next role should change your trajectory.
  </div>
  <div class="promo-badge">ABC Inc Careers</div>
</div>
"""

if not st.session_state.logged_in:
    if st.session_state.auth_view == "register":
        st.markdown(
            """
<div class="section-card">
  <strong>Create your profile.</strong> Register first, then login to continue to your dashboard.
</div>
""",
            unsafe_allow_html=True,
        )

        col_form, col_promo = st.columns([0.65, 0.35])

        with col_form:
            st.subheader("Register")
            if st.button("Back to Login", key="back_to_login"):
                st.session_state.auth_view = "login"
                st.rerun()

            reg_name = st.text_input("Name", key="reg_name")
            reg_phone = st.text_input("Mobile Number", key="reg_phone")
            reg_email = st.text_input("Email", key="reg_email")
            reg_role = st.selectbox("Select Job Position", ["Developer", "Tester", "Analyst"], key="reg_role")

            reg_experience_type = st.radio("Previous Experience", ["Fresher", "Experienced"], key="reg_experience_type")
            reg_experience_years = None
            reg_previous_role = None
            if reg_experience_type == "Experienced":
                reg_experience_years = st.number_input(
                    "Enter years of experience",
                    min_value=1,
                    max_value=40,
                    step=1,
                    key="reg_experience_years",
                )
                reg_previous_role = st.text_input("Previous Job Role", key="reg_previous_role")

            reg_password = st.text_input("Choose a Password", type="password", key="reg_pass")
            reg_password_confirm = st.text_input("Re-enter Password", type="password", key="reg_pass_confirm")
            st.markdown(
                """
<div class="form-hint">
At least 8 characters, uppercase, lowercase, number, special character, and no spaces.
</div>
""",
                unsafe_allow_html=True,
            )

            if st.button("Register", key="register_button"):
                if not reg_name.strip():
                    st.error("Great start. Please add your name to continue registration.")
                elif not reg_phone.strip():
                    st.error("Great start. Please add your mobile number so we can continue.")
                elif not validate_phone(reg_phone):
                    st.error("Great start. Please enter a valid mobile number (10-15 digits).")
                elif not reg_email.strip():
                    st.error("Great start. Please add your email address.")
                elif not validate_email(reg_email):
                    st.error("Great start. Please enter a valid email format.")
                elif reg_experience_type == "Experienced" and not (reg_previous_role or "").strip():
                    st.error("Great start. Please enter your previous job role.")
                elif not reg_password or not reg_password_confirm:
                    st.error("Great start. Please fill both password fields.")
                elif reg_password != reg_password_confirm:
                    st.error("Great start. Passwords should match exactly.")
                else:
                    failures = validate_password(reg_password)
                    if failures:
                        st.error(" ".join(failures))
                    else:
                        username = reg_name.strip()
                        interview_experience = "Fresher"
                        if reg_experience_type == "Experienced":
                            interview_experience = "1-3 years" if reg_experience_years <= 3 else "4-10 years"

                        success, message = register_user(username, reg_password, reg_password_confirm)
                        if success:
                            save_candidate_profile(
                                username,
                                reg_phone.strip(),
                                reg_email.strip(),
                                reg_role,
                                interview_experience,
                                [],
                                reg_experience_years,
                                (reg_previous_role or "").strip() or None,
                            )
                            st.session_state["registration_success_message"] = "Registration successful. You can now log in."
                            st.session_state["login_user"] = username
                            st.session_state.auth_view = "login"
                            st.rerun()
                        else:
                            st.error(message)

        with col_promo:
            st.markdown(promo_card_html, unsafe_allow_html=True)

    else:
        st.markdown(
            """
<div class="section-card">
  <strong>Welcome to ABC Inc.</strong> Please log in to continue.
</div>
""",
            unsafe_allow_html=True,
        )

        if registration_success_message:
            st.success(registration_success_message)

        col_login, col_promo = st.columns([0.55, 0.45])
        with col_login:
            st.subheader("Login to Your Account")
            login_username = st.text_input("Name", key="login_user")
            login_password = st.text_input("Password", type="password", key="login_pass")

            if st.button("Login", key="login_button"):
                if not login_username or not login_password:
                    st.error("Great start. Please enter both name and password.")
                else:
                    success, message = login_user(login_username.strip(), login_password)
                    if success:
                        st.success(message)
                        reset_interview_session_state()
                        st.session_state.logged_in = True
                        st.session_state.username = login_username.strip()
                        st.rerun()
                    else:
                        st.error(message)

            st.markdown("**New user, Build your career with us**")
            if st.button("Register Now", key="register_now_button"):
                st.session_state.auth_view = "register"
                st.rerun()

        with col_promo:
            st.markdown(promo_card_html, unsafe_allow_html=True)

else:
    latest_profile = get_latest_candidate_profile(st.session_state.username)
    active_ban = get_active_ban_status(st.session_state.username)
    interview_attempts = get_candidate_interview_attempts(st.session_state.username)
    selected_result = get_latest_interview_result(st.session_state.username)

    if interview_attempts:
        with st.container(border=True):
            st.markdown("### Interview History")
            attempt_state_key = f"candidate_selected_attempt_id_{st.session_state.username}"
            valid_attempt_ids = [attempt["id"] for attempt in interview_attempts]
            if st.session_state.get(attempt_state_key) not in valid_attempt_ids:
                st.session_state[attempt_state_key] = valid_attempt_ids[0]

            default_index = next(
                (
                    index
                    for index, attempt in enumerate(interview_attempts)
                    if attempt["id"] == st.session_state[attempt_state_key]
                ),
                0,
            )
            selected_label = st.selectbox(
                "Select Interview Attempt",
                options=[attempt["label"] for attempt in interview_attempts],
                index=default_index,
                key=f"candidate_attempt_picker_{st.session_state.username}",
            )
            selected_attempt = next((attempt for attempt in interview_attempts if attempt["label"] == selected_label), interview_attempts[0])
            st.session_state[attempt_state_key] = selected_attempt["id"]
            selected_result = (
                get_interview_result_by_id(st.session_state.username, selected_attempt["id"])
                or selected_result
            )
            st.caption(
                f"Showing attempt {selected_attempt['sequence_no']} of {len(interview_attempts)} "
                f"({selected_attempt['timestamp_label']})."
            )

    if selected_result:
        phone = latest_profile["phone"] if latest_profile and latest_profile["phone"] else "Not provided"
        email = latest_profile["email"] if latest_profile and latest_profile["email"] else "Not provided"
        applied_role = selected_result["role"] if selected_result and selected_result["role"] else (
            latest_profile["role"] if latest_profile and latest_profile["role"] else "Not provided"
        )
        experience_value = (
            selected_result["experience"]
            if selected_result and selected_result["experience"]
            else (
                latest_profile["experience"]
                if latest_profile and latest_profile["experience"]
                else "Not provided"
            )
        )
        previous_role = (
            latest_profile["previous_role"]
            if latest_profile and latest_profile["previous_role"]
            else "Not provided"
        )

        feedback = selected_result.get("feedback")
        answer_rows = selected_result.get("original_answers", [])
        candidate_status = "Banned" if active_ban else "Active"
        candidate_status_class = "banned" if active_ban else "active"

        st.markdown('<a id="overview"></a>', unsafe_allow_html=True)
        st.markdown(
            f"""
<div class="summary-card">
  <div style="font-size: 21px; font-weight: 700;">Profile Overview</div>
  <div class="summary-grid">
    <div class="summary-item"><div class="summary-label">Name</div><div class="summary-value">{_escape_html(st.session_state.username)}</div></div>
    <div class="summary-item"><div class="summary-label">Role</div><div class="summary-value">{_escape_html(applied_role)}</div></div>
    <div class="summary-item"><div class="summary-label">Experience</div><div class="summary-value">{_escape_html(experience_value)}</div></div>
    <div class="summary-item"><div class="summary-label">Status</div><div class="summary-value"><span class="status-pill {candidate_status_class}">{_escape_html(candidate_status)}</span></div></div>
  </div>
  <div class="summary-grid">
    <div class="summary-item"><div class="summary-label">Phone</div><div class="summary-value">{_escape_html(phone)}</div></div>
    <div class="summary-item"><div class="summary-label">Email</div><div class="summary-value">{_escape_html(email)}</div></div>
    <div class="summary-item"><div class="summary-label">Previous Job Role</div><div class="summary-value">{_escape_html(previous_role)}</div></div>
    <div class="summary-item"><div class="summary-label">Interview Result</div><div class="summary-value">{selected_result['score']} / 15</div></div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
        if active_ban:
            st.warning(f"Profile under review until {active_ban['ban_until']}.")
            st.caption(f"Reason: {active_ban['ban_reason']}")

        multi_interview_insights = get_candidate_multi_interview_insights(st.session_state.username)
        with st.container(border=True):
            st.markdown("### Performance Across Interviews")
            st.caption(f"Total interviews completed: {multi_interview_insights['total_attempts']}")
            role_insight_rows = multi_interview_insights.get("role_insights", [])
            if role_insight_rows:
                table_rows = [{key: value for key, value in row.items() if key != "Suggestion"} for row in role_insight_rows]
                st.dataframe(table_rows, width="stretch")
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
                    st.success("Great coverage: this candidate has interview history across Developer, Tester, and Analyst roles.")
            else:
                st.info("Cross-interview suggestions will appear after more interview attempts.")

        with st.container(border=True):
            st.markdown("### Retest for Improvement")
            st.caption("Choose a role, then select one skill card and 2 to 5 specializations for your retest.")
            retest_role_options = ["Developer", "Tester", "Analyst"]
            default_retest_role = applied_role if applied_role in retest_role_options else retest_role_options[0]
            retest_role = st.selectbox("Role for Retest", retest_role_options, index=retest_role_options.index(default_retest_role), key="retest_role")
            retest_skill_map = get_role_skill_map(retest_role)
            if not retest_skill_map:
                st.error("No skill map found for the selected retest role.")
            else:
                st.write("Select one skill box and choose 2 to 5 specializations inside it before starting retest.")
                role_slug = retest_role.lower().replace(" ", "_").replace("/", "_")
                retest_active_key = f"retest_active_skill_{role_slug}"
                retest_skill_options = list(retest_skill_map.keys())
                if (
                    retest_active_key not in st.session_state
                    or st.session_state[retest_active_key] not in retest_skill_options
                ):
                    st.session_state[retest_active_key] = retest_skill_options[0]

                active_retest_skill = st.session_state[retest_active_key]
                retest_skill_cols = st.columns(3, gap="large")
                retest_specialization_selection = {}

                for index, skill_name in enumerate(retest_skill_options):
                    col = retest_skill_cols[index % 3]
                    skill_slug = skill_name.lower().replace(" ", "_").replace("/", "_")

                    with col:
                        is_selected = skill_name == active_retest_skill
                        with st.container(border=True):
                            header_type = "primary" if is_selected else "secondary"
                            if st.button(
                                skill_name,
                                key=f"activate_retest_skill_{role_slug}_{skill_slug}",
                                width="stretch",
                                type=header_type,
                            ):
                                st.session_state[retest_active_key] = skill_name
                                st.rerun()

                            st.markdown("<div class='skill-box-subtitle'>Specializations</div>", unsafe_allow_html=True)

                            specs = retest_skill_map[skill_name]
                            selected_count = sum(
                                1
                                for spec_idx in range(len(specs))
                                if st.session_state.get(f"retest_spec_{role_slug}_{skill_slug}_{spec_idx}", False)
                            )

                            for spec_idx, spec_name in enumerate(specs):
                                spec_key = f"retest_spec_{role_slug}_{skill_slug}_{spec_idx}"
                                is_checked = st.session_state.get(spec_key, False)
                                disable_checkbox = (not is_selected) or (selected_count >= 5 and not is_checked)
                                st.checkbox(spec_name, key=spec_key, disabled=disable_checkbox)

                            selected_specs = [
                                spec_name
                                for spec_idx, spec_name in enumerate(specs)
                                if st.session_state.get(f"retest_spec_{role_slug}_{skill_slug}_{spec_idx}", False)
                            ]
                            retest_specialization_selection[skill_name] = selected_specs

                            if is_selected:
                                count_class = "ok" if 2 <= len(selected_specs) <= 5 else "warn"
                                st.markdown(
                                    f"<div class='specialization-count {count_class}'>Selected: {len(selected_specs)} / 5 (minimum 2)</div>",
                                    unsafe_allow_html=True,
                                )

                active_retest_skill = st.session_state[retest_active_key]
                selected_retest_specs = retest_specialization_selection.get(active_retest_skill, [])

                if feedback and feedback.get("top_missing_keywords"):
                    keyword_badges = "".join(
                        [
                            f"<span class='keyword-chip warning'>{_escape_html(keyword)}</span>"
                            for keyword in feedback["top_missing_keywords"][:8]
                        ]
                    )
                    st.markdown(
                        f"<div class='keyword-chip-row'><strong>Missed keywords to improve:</strong> {keyword_badges}</div>",
                        unsafe_allow_html=True,
                    )

                if st.button("Start Retest", key="start_retest_interview_button"):
                    if active_ban:
                        st.error("Interview access is currently unavailable for this profile. Please contact support.")
                    elif len(selected_retest_specs) < 2:
                        st.error("Please select at least 2 specializations for retest.")
                    elif len(selected_retest_specs) > 5:
                        st.error("Please select at most 5 specializations for retest.")
                    else:
                        retest_skill_payload = build_selected_skill_payload(
                            [active_retest_skill],
                            {active_retest_skill: selected_retest_specs},
                        )
                        update_candidate_skills(st.session_state.username, retest_skill_payload)
                        reset_interview_session_state()
                        st.session_state.role = retest_role
                        st.session_state.experience = experience_value
                        st.session_state.selected_primary_skill = active_retest_skill
                        st.session_state.selected_specializations = selected_retest_specs
                        st.session_state.current_index = 0
                        st.session_state.answers = {}
                        st.session_state.answer_drafts = {}
                        st.session_state.interview_submitted = False
                        st.session_state.results_summary = None
                        st.session_state.results_saved = False
                        st.session_state.allow_retest = True
                        st.switch_page("pages/interview.py")

        st.markdown('<a id="scores"></a>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("### Scores")
            if feedback:
                metric_col1, metric_col2, metric_col3 = st.columns(3)
                with metric_col1:
                    st.metric("Average Relevance", f"{feedback['avg_relevance']:.1f}%")
                    render_score_meter("Relevance", feedback["avg_relevance"], tone="brand")
                with metric_col2:
                    st.metric("Average Confidence", f"{feedback['avg_confidence']:.1f}%")
                    render_score_meter("Confidence", feedback["avg_confidence"], tone="success")
                with metric_col3:
                    hard_relevance_text = "N/A"
                    hard_relevance_value = 0.0
                    if feedback["hard_avg_relevance"] is not None:
                        hard_relevance_value = feedback["hard_avg_relevance"]
                        hard_relevance_text = f"{hard_relevance_value:.1f}%"
                    st.metric("Hard Question Relevance", hard_relevance_text)
                    render_score_meter("Hard Question Relevance", hard_relevance_value, tone="warning")
            else:
                st.info("Great start. Detailed score breakdown will appear after your next interview.")

        st.markdown('<a id="suggestions"></a>', unsafe_allow_html=True)
        with st.container(border=True):
            st.subheader("Smart Insights")
            if feedback:
                insight_col1, insight_col2 = st.columns(2)
                with insight_col1:
                    st.markdown("✅ **Strengths**")
                    for strength in feedback["strengths"]:
                        st.write(f"- {strength}")
                with insight_col2:
                    st.markdown("⚠️ **Improvement Areas**")
                    for improvement in feedback["improvements"]:
                        st.write(f"- {improvement}")

                if feedback["topic_analysis"]:
                    st.markdown("**Topic Analysis**")
                    st.dataframe(feedback["topic_analysis"], width="stretch")

                if feedback["top_missing_keywords"]:
                    keyword_badges = "".join(
                        [
                            f"<span class='keyword-chip warning'>{_escape_html(keyword)}</span>"
                            for keyword in feedback["top_missing_keywords"][:8]
                        ]
                    )
                    st.markdown(
                        f"<div class='keyword-chip-row'><strong>Frequently missed keywords:</strong> {keyword_badges}</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.info("Great start. Suggestions will appear after your next interview submission.")

        if answer_rows:
            render_answer_level_insights(answer_rows)
        else:
            st.info("Great start. Answer-level insights will appear after your next interview submission.")

        st.success("Our team will contact you soon.")

        if st.button("Logout", key="logout_button_completed"):
            reset_interview_session_state()
            st.session_state.logged_in = False
            st.session_state.username = None
            st.session_state.auth_view = "login"
            st.rerun()

    else:
        st.header(f"Welcome {st.session_state.username}")

        if not latest_profile:
            st.error("Great start. We could not find your profile yet. Please register again.")
            if st.button("Go to Registration", key="profile_missing_register"):
                reset_interview_session_state()
                st.session_state.logged_in = False
                st.session_state.username = None
                st.session_state.auth_view = "register"
                st.rerun()
        else:
            phone = latest_profile["phone"] or "Not provided"
            email = latest_profile["email"] or "Not provided"
            applied_role = latest_profile["role"]
            experience_value = latest_profile["experience"]
            previous_role = latest_profile["previous_role"] or "Not provided"

            pending_status = "Banned" if active_ban else "Interview Pending"
            pending_status_class = "banned" if active_ban else "active"

            st.markdown('<a id="overview"></a>', unsafe_allow_html=True)
            st.markdown(
                f"""
<div class="summary-card">
  <div style="font-size: 21px; font-weight: 700;">Profile Overview</div>
  <div class="summary-grid">
    <div class="summary-item"><div class="summary-label">Name</div><div class="summary-value">{_escape_html(st.session_state.username)}</div></div>
    <div class="summary-item"><div class="summary-label">Role</div><div class="summary-value">{_escape_html(applied_role)}</div></div>
    <div class="summary-item"><div class="summary-label">Experience</div><div class="summary-value">{_escape_html(experience_value)}</div></div>
    <div class="summary-item"><div class="summary-label">Status</div><div class="summary-value"><span class="status-pill {pending_status_class}">{_escape_html(pending_status)}</span></div></div>
  </div>
  <div class="summary-grid">
    <div class="summary-item"><div class="summary-label">Phone</div><div class="summary-value">{_escape_html(phone)}</div></div>
    <div class="summary-item"><div class="summary-label">Email</div><div class="summary-value">{_escape_html(email)}</div></div>
    <div class="summary-item"><div class="summary-label">Previous Job Role</div><div class="summary-value">{_escape_html(previous_role)}</div></div>
    <div class="summary-item"><div class="summary-label">Interview Result</div><div class="summary-value">Pending</div></div>
  </div>
</div>
""",
                unsafe_allow_html=True,
            )

            st.markdown('<a id="candidate-dashboard"></a>', unsafe_allow_html=True)
            dashboard_title_col, dashboard_logout_col = st.columns([0.78, 0.22])
            with dashboard_title_col:
                st.subheader("Dashboard")
            with dashboard_logout_col:
                if st.button("Logout", key="logout_button_dashboard_top"):
                    reset_interview_session_state()
                    st.session_state.logged_in = False
                    st.session_state.username = None
                    st.session_state.auth_view = "login"
                    st.rerun()
            st.write("Select one skill box and choose 2 to 5 specializations inside it before starting the interview.")

            role_skill_map = get_role_skill_map(applied_role)
            if not role_skill_map:
                st.error("No skill mapping found for the selected role.")
            else:
                skill_options = list(role_skill_map.keys())
                if (
                    "dashboard_active_skill" not in st.session_state
                    or st.session_state.dashboard_active_skill not in skill_options
                ):
                    st.session_state.dashboard_active_skill = skill_options[0]

                active_skill = st.session_state.dashboard_active_skill
                skill_cols = st.columns(3, gap="large")
                specialization_selection = {}

                for index, skill_name in enumerate(skill_options):
                    col = skill_cols[index % 3]
                    skill_slug = skill_name.lower().replace(" ", "_").replace("/", "_")

                    with col:
                        is_selected = skill_name == active_skill
                        with st.container(border=True):
                            header_type = "primary" if is_selected else "secondary"
                            if st.button(
                                skill_name,
                                key=f"activate_skill_{skill_slug}",
                                width="stretch",
                                type=header_type,
                            ):
                                st.session_state.dashboard_active_skill = skill_name
                                st.rerun()

                            st.markdown("<div class='skill-box-subtitle'>Specializations</div>", unsafe_allow_html=True)

                            specs = role_skill_map[skill_name]
                            selected_count = sum(
                                1
                                for spec_idx in range(len(specs))
                                if st.session_state.get(f"spec_{skill_slug}_{spec_idx}", False)
                            )

                            for spec_idx, spec_name in enumerate(specs):
                                spec_key = f"spec_{skill_slug}_{spec_idx}"
                                is_checked = st.session_state.get(spec_key, False)
                                disable_checkbox = (not is_selected) or (selected_count >= 5 and not is_checked)
                                st.checkbox(spec_name, key=spec_key, disabled=disable_checkbox)

                            selected_specs = [
                                spec_name
                                for spec_idx, spec_name in enumerate(specs)
                                if st.session_state.get(f"spec_{skill_slug}_{spec_idx}", False)
                            ]
                            specialization_selection[skill_name] = selected_specs

                            if is_selected:
                                count_class = "ok" if 2 <= len(selected_specs) <= 5 else "warn"
                                st.markdown(
                                    f"<div class='specialization-count {count_class}'>Selected: {len(selected_specs)} / 5 (minimum 2)</div>",
                                    unsafe_allow_html=True,
                                )

                active_skill = st.session_state.dashboard_active_skill
                selected_specs = specialization_selection.get(active_skill, [])

                if st.button(
                    "Submit and Start Interview",
                    key="start_interview_button",
                ):
                    if active_ban:
                        st.error("Great start. Interview access is currently unavailable for this profile. Please contact support.")
                    elif len(selected_specs) < 2:
                        st.error(f"Great start. Please select at least 2 specializations for {active_skill}.")
                    elif len(selected_specs) > 5:
                        st.error(f"Great start. You can select at most 5 specializations for {active_skill}.")
                    else:
                        selected_skill_payload = build_selected_skill_payload(
                            [active_skill],
                            {active_skill: selected_specs},
                        )
                        update_candidate_skills(st.session_state.username, selected_skill_payload)

                        reset_interview_session_state()
                        st.session_state.role = applied_role
                        st.session_state.experience = experience_value
                        st.session_state.selected_primary_skill = active_skill
                        st.session_state.selected_specializations = selected_specs
                        st.session_state.current_index = 0
                        st.session_state.answers = {}
                        st.session_state.answer_drafts = {}
                        st.session_state.interview_submitted = False
                        st.session_state.results_summary = None
                        st.session_state.results_saved = False
                        st.session_state.allow_retest = False
                        st.switch_page("pages/interview.py")
