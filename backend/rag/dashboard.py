"""The admin dashboard's figures, from DATA_DIR/feedback (questions, unanswered, ratings) and the users file.

Times are shown in DASHBOARD_TIMEZONE (default Asia/Kolkata), whatever the server's clock is set to.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from rag.admin_answers import AnswerStore, question_key
from rag.feedback import FeedbackLog


def _group(entries: list[dict]) -> list[dict]:
    """One row per question (ignoring capitals and punctuation): how often, and when last asked."""
    counts: Counter[str] = Counter()
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    for entry in entries:
        key = question_key(entry["question"])
        if not key:
            continue
        counts[key] += 1
        first.setdefault(key, entry["question"])
        last[key] = max(last.get(key, ""), entry["at"])
    return [{"key": k, "question": first[k], "count": n, "last_asked": last[k]} for k, n in counts.most_common()]


def build_dashboard(settings, feedback: FeedbackLog | None, users_count: int = 0, days: int = 30) -> dict:
    tz = ZoneInfo(settings.dashboard_timezone)
    now = datetime.now(tz)
    since = now - timedelta(days=days)
    log = feedback or FeedbackLog(settings.data_dir / "feedback")
    questions = log._read("questions.jsonl", since)
    unanswered = log._read("unanswered.jsonl", None)
    ratings = log._read("ratings.jsonl", since)
    resolved = AnswerStore(settings.data_dir / "admin").resolved_keys()

    def local(entry: dict) -> datetime:
        return datetime.fromisoformat(entry["at"]).astimezone(tz)

    by_hour = [0] * 24
    by_weekday = [0] * 7
    by_day: dict[str, int] = defaultdict(int)
    for entry in questions:
        at = local(entry)
        by_hour[at.hour] += 1
        by_weekday[at.weekday()] += 1
        by_day[at.strftime("%Y-%m-%d")] += 1
    daily = [{"date": (now - timedelta(days=i)).strftime("%Y-%m-%d"),
              "count": by_day.get((now - timedelta(days=i)).strftime("%Y-%m-%d"), 0)} for i in range(days - 1, -1, -1)]
    times = [e["seconds"] for e in questions if isinstance(e.get("seconds"), (int, float))]
    answered = sum(e.get("mode") not in ("no_answer", "error") for e in questions)
    today = now.strftime("%Y-%m-%d")

    open_questions = []
    for row in _group(unanswered):
        row["answered"] = row["key"] in resolved
        open_questions.append(row)
    open_questions.sort(key=lambda r: (r["answered"], -r["count"]))

    return {
        "timezone": settings.dashboard_timezone,
        "days": days,
        "totals": {
            "questions": len(questions),
            "today": by_day.get(today, 0),
            "last_7_days": sum(1 for e in questions if local(e) >= now - timedelta(days=7)),
            "answered_share": round(100 * answered / len(questions)) if questions else None,
            "unanswered_open": sum(not r["answered"] for r in open_questions),
            "users": users_count,
            "helpful": sum(r.get("rating") == "up" for r in ratings),
            "not_helpful": sum(r.get("rating") == "down" for r in ratings),
            "avg_seconds": round(sum(times) / len(times), 1) if times else None,
            "median_seconds": round(median(times), 1) if times else None,
        },
        "top_questions": _group(questions)[:20],
        "by_hour": by_hour,
        "by_weekday": by_weekday,
        "daily": daily,
        "busiest_hour": max(range(24), key=lambda h: by_hour[h]) if questions else None,
        "unanswered": open_questions[:200],
        "not_helpful": [{"at": r["at"], "question": r["question"], "comment": r.get("comment", "")}
                        for r in ratings if r.get("rating") == "down"][-50:][::-1],
    }


