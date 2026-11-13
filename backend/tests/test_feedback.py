from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from rag.api.app import create_app
from rag.feedback import FeedbackLog, Report, scrub, seconds_until, send_report


def test_personal_details_are_masked():
    text = scrub("My son's number is 98765 43210, mail me at parent.name@gmail.com. Cut off 182.5, rank 4680")
    assert "98765" not in text and "gmail" not in text
    assert "[phone]" in text and "[email]" in text and "182.5" in text and "4680" in text


def test_unanswered_questions_and_ratings_are_reported_once(tmp_path):
    log = FeedbackLog(tmp_path)
    log.unanswered("What is the canteen menu on Friday?")
    log.unanswered("what is the canteen menu on friday")
    log.unanswered("Is there a swimming pool?")
    log.rating("Hostel fees?", "The hostel fee is ...", "down", "no amount given")
    log.rating("Counselling code?", "4680", "up")
    report = log.report()
    assert report.subject.endswith("3 unanswered questions, 1 not helpful")
    text = report.text()
    assert "(asked 2 times)" in text and "swimming pool" in text and "no amount given" in text
    assert "Answers marked helpful: 1" in text and "<ol>" in report.html()

    settings = mock.Mock(report_email_to=["office@example.org"], smtp_host="smtp.example.org", smtp_port=587,
                         smtp_user="bot@example.org", smtp_password="app-password", smtp_from="")
    with mock.patch("rag.feedback.smtplib.SMTP") as smtp:
        sent = send_report(settings, log)
        server = smtp.return_value.__enter__.return_value
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("bot@example.org", "app-password")
        message = server.send_message.call_args[0][0]
        assert message["To"] == "office@example.org" and message["Subject"] == sent.subject
        # nothing new since: no second email
        assert send_report(settings, log).empty and server.send_message.call_count == 1


def test_the_report_runs_at_the_set_hour():
    now = datetime(2026, 11, 12, 17, 30).astimezone()
    assert seconds_until(18, now) == 30 * 60
    assert seconds_until(9, now) == timedelta(hours=15, minutes=30).total_seconds()


def test_the_api_saves_ratings_and_unanswered_questions(pipeline, services):
    app = create_app(pipeline.settings.model_copy(update={"rate_limit_per_minute": 0}), services=services)
    folder = pipeline.settings.data_dir / "feedback"
    with TestClient(app) as client:
        assert client.post("/api/feedback", json={"question": "Hostel?", "answer": "Yes", "rating": "up"}).json() == {"ok": True}
        assert client.post("/api/feedback", json={"question": "Hostel?", "rating": "maybe"}).status_code == 422
        body = client.post("/api/chat", json={"message": "zzqx wvvy plorp"}).json()
        assert body["mode"] == "no_answer"
    report = FeedbackLog(folder).report()
    assert [r["rating"] for r in report.ratings][-1] == "up"
    assert report.unanswered[-1]["question"] == "zzqx wvvy plorp"
    assert isinstance(report, Report)


def test_the_live_check_reports_what_the_real_setup_answers(services, tmp_path):
    import asyncio

    from rag.eval.answer_eval import AnswerCase
    from rag.eval.live_eval import run_live, write_report

    cases = [AnswerCase("What are the library timings?", ["8:00 AM"]), AnswerCase("zzqx wvvy plorp", ["never"])]
    report = asyncio.run(run_live(services.answers, cases, pause=0, progress=lambda *_: None))
    assert report.passed == 1 and [r["mode"] for r in report.results][1] == "no_answer"
    text = write_report(report, tmp_path).read_text(encoding="utf-8")
    assert "1 of 2 answers contain the expected fact" in text and "### zzqx wvvy plorp" in text and "| ✅ |" in text
