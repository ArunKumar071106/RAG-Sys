"""Keeping the knowledge base up to date without anyone running commands.

Every REFRESH_EVERY_DAYS days (e.g. 30 = monthly), at REFRESH_HOUR at night, the website is crawled
again and the changed pages are extracted, chunked and indexed (incremental: unchanged pages are not
embedded again, removed pages are deleted). The admin gets an email saying what changed, or what went
wrong, when REPORT_EMAIL_TO and the SMTP account are set.

Two ways to run it:
  * inside the API (the server running all the time): REFRESH_EVERY_DAYS=30 in .env, nothing else;
  * from a scheduler (Windows Task Scheduler, cron): `python -m rag.cli refresh`, e.g. on the 1st of
    each month; see scripts/refresh.ps1 and scripts/refresh.sh.

A refresh missed because the server was off runs at the next REFRESH_HOUR after it was due.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

STATE_FILE = "refresh_state.json"


def _now() -> datetime:
    return datetime.now().astimezone()


@dataclass
class RefreshResult:
    ok: bool
    started_at: datetime
    finished_at: datetime
    report: dict = field(default_factory=dict)
    error: str = ""

    @property
    def minutes(self) -> int:
        return max(1, round((self.finished_at - self.started_at).total_seconds() / 60))

    def subject(self) -> str:
        day = self.finished_at.strftime("%d %b %Y")
        if not self.ok:
            return f"Arivazhai: the website update FAILED ({day})"
        changed = (self.report.get("index") or {}).get("text", {}).get("changed_documents")
        if changed is None:
            return f"Arivazhai: knowledge base updated ({day})"
        return f"Arivazhai: knowledge base updated, {changed} page{'' if changed == 1 else 's'} changed ({day})"

    def text(self) -> str:
        lines = [self.subject(), ""]
        if not self.ok:
            lines += [
                "The monthly update of the answers from the official website did not finish:",
                f"  {self.error or 'unknown error'}",
                "",
                "The assistant keeps answering from the previous version of the website.",
                "Check the server log, then run it again: python -m rag.cli refresh (in the backend folder).",
            ]
        else:
            index = self.report.get("index") or {}
            text = index.get("text") or {}
            images = index.get("images") or {}
            lines += [
                "The assistant now answers from the current official website.",
                "",
                f"  Pages read:            {self.report.get('documents', '-')}",
                f"  Pages changed:         {text.get('changed_documents', '-')}",
                f"  Pages removed:         {text.get('removed_documents', '-')}",
                f"  Text passages updated: {text.get('upserted', '-')} (removed {text.get('deleted', '-')})",
                f"  Images:                {self.report.get('images', '-')} (updated {images.get('upserted', '-')})",
            ]
        lines += ["", f"Started {self.started_at:%d %b %Y %H:%M}, took about {self.minutes} min."]
        return "\n".join(lines)


# ------------------------------------------------------------------ when
def state_path(settings) -> Path:
    return Path(settings.data_dir) / STATE_FILE


def last_refresh(settings) -> datetime | None:
    """When the last refresh finished (successfully or not), from data/refresh_state.json."""
    try:
        data = json.loads(state_path(settings).read_text(encoding="utf-8"))
        return datetime.fromisoformat(data["finished_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_result(settings, result: RefreshResult) -> None:
    path = state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"ok": result.ok, "started_at": result.started_at.isoformat(timespec="seconds"),
            "finished_at": result.finished_at.isoformat(timespec="seconds"), "error": result.error,
            "report": result.report}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def next_refresh(settings, last: datetime | None, now: datetime | None = None) -> datetime:
    """The next REFRESH_HOUR on or after `last + REFRESH_EVERY_DAYS`. Never refreshed: tonight."""
    now = now or _now()
    due = (last + timedelta(days=settings.refresh_every_days)) if last else now
    due = max(due, now)
    at = due.replace(hour=settings.refresh_hour, minute=0, second=0, microsecond=0)
    if at < due:
        at += timedelta(days=1)
    return at


# ------------------------------------------------------------------ telling the admin
def notify(settings, result: RefreshResult) -> bool:
    """Email the admin (REPORT_EMAIL_TO) what the refresh did. False when no email is set up or it failed."""
    from rag.feedback import email_configured, send_email

    if not email_configured(settings):
        return False
    try:
        send_email(settings, result.subject(), result.text())
        log.info("Refresh report emailed to %s", ", ".join(settings.report_email_to))
        return True
    except Exception as exc:  # a wrong password or no network must not hide the refresh itself
        log.warning("Could not email the refresh report: %s", exc)
        return False


# ------------------------------------------------------------------ running it
def run_refresh(settings, run=None) -> RefreshResult:
    """Crawl the website again and index what changed (the command-line way: no server needed)."""
    if run is None:
        from rag.pipeline import run_pipeline as run
    started = _now()
    try:
        report = run(settings, ("crawl", "extract", "images", "chunk", "index"), full=False)
        result = RefreshResult(True, started, _now(), report=report)
    except Exception as exc:
        log.exception("Refresh failed")
        result = RefreshResult(False, started, _now(), error=str(exc))
    save_result(settings, result)
    notify(settings, result)
    return result


async def _refresh_in_server(settings, services) -> RefreshResult:
    """The same, through the server's reindex job: the running assistant picks up the new index."""
    started = _now()
    try:
        job = services.start_reindex(full=False, recrawl=True)
    except RuntimeError as exc:  # still starting up, or an admin started a reindex by hand
        log.info("Refresh postponed: %s", exc)
        raise
    while job.state in ("queued", "running"):
        await asyncio.sleep(30)
    ok = job.state == "finished"
    result = RefreshResult(ok, started, _now(), report=job.report if ok else {}, error=job.error)
    save_result(settings, result)
    await asyncio.to_thread(notify, settings, result)
    return result


async def scheduled_refreshes(settings, services) -> None:
    """Background task of the API: refresh every REFRESH_EVERY_DAYS days while the server runs."""
    while True:
        at = next_refresh(settings, last_refresh(settings))
        log.info("Next website refresh: %s", at.strftime("%d %b %Y %H:%M"))
        # wake up at least hourly: the clock may jump (sleep, daylight saving) while we wait
        while (wait := (at - _now()).total_seconds()) > 0:
            await asyncio.sleep(min(wait, 3600))
        try:
            await _refresh_in_server(settings, services)
        except RuntimeError:
            await asyncio.sleep(1800)  # busy: try again in half an hour
        except Exception as exc:
            log.warning("Website refresh failed to start: %s", exc)
            await asyncio.sleep(3600)
