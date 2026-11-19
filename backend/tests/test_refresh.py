import asyncio
from datetime import datetime, timedelta, timezone
from unittest import mock

from rag.refresh import RefreshResult, _refresh_in_server, last_refresh, next_refresh, run_refresh

TZ = timezone(timedelta(hours=5, minutes=30))
REPORT = {"documents": 120, "images": 40, "chunks": 900,
          "index": {"text": {"changed_documents": 3, "removed_documents": 1, "upserted": 25, "deleted": 9},
                    "images": {"upserted": 2}}}


def schedule(every=30, hour=2):
    return mock.Mock(refresh_every_days=every, refresh_hour=hour)


def test_next_refresh_is_at_night_after_the_interval():
    now = datetime(2026, 11, 19, 15, 0, tzinfo=TZ)
    last = datetime(2026, 11, 1, 2, 40, tzinfo=TZ)
    assert next_refresh(schedule(), last, now) == datetime(2026, 12, 2, 2, 0, tzinfo=TZ)  # 1 Dec 02:40 has passed 02:00


def test_never_refreshed_or_overdue_runs_the_coming_night():
    now = datetime(2026, 11, 19, 15, 0, tzinfo=TZ)
    tonight = datetime(2026, 11, 20, 2, 0, tzinfo=TZ)
    assert next_refresh(schedule(), None, now) == tonight
    assert next_refresh(schedule(), now - timedelta(days=90), now) == tonight  # the server was off: catch up
    early = datetime(2026, 11, 19, 1, 0, tzinfo=TZ)
    assert next_refresh(schedule(), None, early) == datetime(2026, 11, 19, 2, 0, tzinfo=TZ)


def test_a_refresh_is_recorded_and_the_admin_is_told_what_changed(settings):
    pipeline = mock.Mock(return_value=REPORT)
    with mock.patch("rag.refresh.notify") as notify:
        result = run_refresh(settings, run=pipeline)
    stages = pipeline.call_args.args[1]
    assert stages == ("crawl", "extract", "images", "chunk", "index") and pipeline.call_args.kwargs == {"full": False}
    assert result.ok and notify.call_args.args[1] is result
    assert "3 pages changed" in result.subject()
    text = result.text()
    assert "Pages read:            120" in text and "Pages removed:         1" in text
    assert last_refresh(settings) is not None


def test_a_failed_refresh_says_so_and_keeps_the_old_answers(settings):
    with mock.patch("rag.refresh.notify"):
        result = run_refresh(settings, run=mock.Mock(side_effect=RuntimeError("Crawl failed or returned no pages")))
    assert not result.ok and "FAILED" in result.subject()
    assert "Crawl failed" in result.text() and "previous version of the website" in result.text()
    assert last_refresh(settings) is not None  # a failure waits for the next month too, instead of retrying all night


def test_no_email_set_up_means_no_email(settings):
    from rag.refresh import notify

    started = datetime.now(TZ)
    with mock.patch("rag.feedback.send_email") as send:
        assert notify(settings, RefreshResult(True, started, started, report=REPORT)) is False
    send.assert_not_called()


def test_the_running_server_refreshes_through_its_reindex_job(settings):
    job = mock.Mock(state="finished", report=REPORT, error="")
    services = mock.Mock()
    services.start_reindex.return_value = job
    with mock.patch("rag.refresh.notify") as notify:
        result = asyncio.run(_refresh_in_server(settings, services))
    services.start_reindex.assert_called_once_with(full=False, recrawl=True)
    assert result.ok and result.report == REPORT and notify.called


def test_refresh_command_shows_when_it_runs(settings, capsys, monkeypatch):
    from rag import cli

    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    assert cli.main(["refresh", "--when"]) == 0
    assert '"last_refresh": null' in capsys.readouterr().out


def test_the_server_runs_the_monthly_refresh_only_when_switched_on(pipeline, services):
    from fastapi.testclient import TestClient

    from rag.api.app import create_app

    started = []

    async def fake_refreshes(settings, running_services):
        started.append((settings.refresh_every_days, running_services))
        await asyncio.Event().wait()  # sleeps until the server stops

    with mock.patch("rag.api.app.scheduled_refreshes", fake_refreshes):
        for every in (0, 30):
            app = create_app(pipeline.settings.model_copy(update={"refresh_every_days": every}), services=services)
            with TestClient(app) as client:
                assert client.get("/api/health").status_code == 200
    assert started == [(30, services)]
