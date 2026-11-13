"""What students and parents asked that Arivazhai could not answer, and how they rated the answers.

* Every question the website does not answer ("I couldn't find this") and every 👍 / 👎 on an
  answer is saved in DATA_DIR/feedback/ (one JSON line each). Phone numbers and email addresses
  typed into a question are masked before saving; no IP address or name is kept.
* Once a day (REPORT_HOUR, the server's local time) the new entries are emailed as one summary to
  REPORT_EMAIL_TO, through SMTP (a Gmail app password works). The admission office can then add
  the missing answers to the website. `python -m rag.cli feedback-report` prints or sends it at once.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import smtplib
import ssl
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.message import EmailMessage
from html import escape
from pathlib import Path

log = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s-]{6,}\d(?!\w)")


def scrub(text: str, limit: int = 600) -> str:
    """Text safe to keep: email addresses and phone numbers masked, cut to `limit` characters."""
    text = _EMAIL_RE.sub("[email]", text or "")
    text = _PHONE_RE.sub(lambda m: "[phone]" if sum(ch.isdigit() for ch in m.group(0)) >= 7 else m.group(0), text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _now() -> datetime:
    return datetime.now().astimezone()


class FeedbackLog:
    """Append-only JSON-lines files: unanswered.jsonl and ratings.jsonl."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self._lock = threading.Lock()

    def _append(self, name: str, entry: dict) -> None:
        try:
            with self._lock:
                self.folder.mkdir(parents=True, exist_ok=True)
                with open(self.folder / name, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:  # a full or read-only disk must never break an answer
            log.warning("Could not save feedback: %s", exc)

    def unanswered(self, question: str, searched: str = "") -> None:
        self._append("unanswered.jsonl", {"at": _now().isoformat(timespec="seconds"), "question": scrub(question, 500),
                                          "searched": scrub(searched, 300)})

    def rating(self, question: str, answer: str, rating: str, comment: str = "") -> None:
        self._append("ratings.jsonl", {"at": _now().isoformat(timespec="seconds"), "rating": rating,
                                       "question": scrub(question, 500), "answer": scrub(answer, 600),
                                       "comment": scrub(comment, 500)})

    def _read(self, name: str, since: datetime | None) -> list[dict]:
        path = self.folder / name
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
                if since is None or datetime.fromisoformat(entry["at"]) > since:
                    out.append(entry)
            except (ValueError, KeyError):
                continue
        return out

    def report(self, since: datetime | None = None) -> Report:
        return Report(since=since, until=_now(), unanswered=self._read("unanswered.jsonl", since),
                      ratings=self._read("ratings.jsonl", since))

    # the time of the last emailed report: the next one starts there
    def last_sent(self) -> datetime | None:
        try:
            return datetime.fromisoformat(json.loads((self.folder / "report_state.json").read_text(encoding="utf-8"))["last_sent"])
        except (OSError, ValueError, KeyError):
            return None

    def mark_sent(self, when: datetime) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "report_state.json").write_text(json.dumps({"last_sent": when.isoformat(timespec="seconds")}),
                                                       encoding="utf-8")


@dataclass
class Report:
    since: datetime | None
    until: datetime
    unanswered: list[dict] = field(default_factory=list)
    ratings: list[dict] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.unanswered and not self.ratings

    def _grouped(self) -> list[tuple[str, int]]:
        """The same question asked several times is listed once, with how often it was asked."""
        counts: Counter[str] = Counter()
        first: dict[str, str] = {}
        for entry in self.unanswered:
            key = re.sub(r"[^a-z0-9]+", " ", entry["question"].lower()).strip()
            counts[key] += 1
            first.setdefault(key, entry["question"])
        return [(first[k], n) for k, n in counts.most_common()]

    @property
    def subject(self) -> str:
        down = sum(r["rating"] == "down" for r in self.ratings)
        return (f"Arivazhai report {self.until:%d %b %Y}: {len(self.unanswered)} unanswered question"
                f"{'' if len(self.unanswered) == 1 else 's'}, {down} not helpful")

    def text(self) -> str:
        period = f"since {self.since:%d %b %Y %H:%M}" if self.since else "so far"
        up = [r for r in self.ratings if r["rating"] == "up"]
        down = [r for r in self.ratings if r["rating"] == "down"]
        lines = [f"Arivazhai, the AAACET admission assistant: what people asked {period}.", ""]
        lines.append(f"Questions it could not answer from the website ({len(self.unanswered)}):")
        lines += [f"  - {q}" + (f"  (asked {n} times)" if n > 1 else "") for q, n in self._grouped()] or ["  none"]
        lines += ["", f"Answers marked not helpful ({len(down)}):"]
        for r in down:
            lines.append(f"  - Q: {r['question']}")
            if r.get("comment"):
                lines.append(f"    Comment: {r['comment']}")
            lines.append(f"    Answer given: {r['answer'][:300]}")
        if not down:
            lines.append("  none")
        lines += ["", f"Answers marked helpful: {len(up)}", "",
                  "Adding the missing information to the official website (or the admission FAQ) lets Arivazhai answer it",
                  "after the next re-crawl. Phone numbers and email addresses typed by visitors are masked."]
        return "\n".join(lines)

    def html(self) -> str:
        items = "".join(f"<li>{escape(q)}{f' <b>(asked {n} times)</b>' if n > 1 else ''}</li>" for q, n in self._grouped())
        downs = "".join(
            f"<li><b>{escape(r['question'])}</b>"
            + (f"<br>Comment: {escape(r['comment'])}" if r.get("comment") else "")
            + f"<br><span style='color:#5b6472'>Answer given: {escape(r['answer'][:300])}</span></li>"
            for r in self.ratings if r["rating"] == "down")
        up = sum(r["rating"] == "up" for r in self.ratings)
        return (f"<div style='font-family:Arial,sans-serif;color:#2d2d2d'><h2 style='color:#323496'>Arivazhai report</h2>"
                f"<h3>Questions it could not answer ({len(self.unanswered)})</h3><ol>{items or '<li>none</li>'}</ol>"
                f"<h3>Answers marked not helpful</h3><ol>{downs or '<li>none</li>'}</ol>"
                f"<p>Answers marked helpful: {up}</p><p style='color:#5b6472;font-size:13px'>Adding the missing information "
                f"to the official website lets Arivazhai answer it after the next re-crawl. Phone numbers and email "
                f"addresses typed by visitors are masked.</p></div>")


def email_configured(settings) -> bool:
    return bool(settings.report_email_to and settings.smtp_host and settings.smtp_user and settings.smtp_password)


def send_email(settings, subject: str, text: str, html: str = "") -> None:
    """Send through SMTP: STARTTLS on port 587 (Gmail: smtp.gmail.com with an app password), SSL on 465."""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = ", ".join(settings.report_email_to)
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    context = ssl.create_default_context()
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=30) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.starttls(context=context)
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)


def send_report(settings, feedback: FeedbackLog, force: bool = False) -> Report:
    """Email what is new since the last report (nothing is sent when nothing is new, unless forced)."""
    report = feedback.report(feedback.last_sent())
    if report.empty and not force:
        return report
    send_email(settings, report.subject, report.text(), report.html())
    feedback.mark_sent(report.until)
    return report


def seconds_until(hour: int, now: datetime | None = None) -> float:
    now = now or _now()
    at = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if at <= now:
        at += timedelta(days=1)
    return (at - now).total_seconds()


async def daily_reports(settings, feedback: FeedbackLog) -> None:
    """Background task of the API: the report every day at REPORT_HOUR, while the server runs."""
    while True:
        await asyncio.sleep(seconds_until(settings.report_hour))
        try:
            report = await asyncio.to_thread(send_report, settings, feedback)
            if not report.empty:
                log.info("Daily report emailed to %s", ", ".join(settings.report_email_to))
        except Exception as exc:  # a wrong password or no network must not stop the server
            log.warning("Could not email the daily report: %s", exc)
