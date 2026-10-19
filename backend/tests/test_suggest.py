from fastapi.testclient import TestClient

from rag.api.app import create_app
from rag.retrieval.corpus import Corpus
from rag.retrieval.suggest import COMMON_QUESTIONS, Suggester
from tests.conftest import make_settings


def make_suggester(tmp_path, departments=("Artificial Intelligence and Data Science", "Mechanical Engineering")):
    settings = make_settings(tmp_path / "data", departments=list(departments))
    return Suggester.build(settings, Corpus())


def test_every_typed_word_starts_a_word_of_the_suggestion(tmp_path):
    suggester = make_suggester(tmp_path)
    assert suggester.suggest("hos") == ["Show photos of the hostel", "What hostel facilities are available?",
                                        "Does the college have hostel facilities for boys and girls?"]
    assert suggester.suggest("hostel boys") == ["Does the college have hostel facilities for boys and girls?"]
    assert suggester.suggest("zzz") == [] and suggester.suggest("h") == []


def test_department_short_forms_are_understood(tmp_path):
    suggester = make_suggester(tmp_path)
    assert suggester.suggest("ai&ds fac") == ["Who are the faculty of the Artificial Intelligence and Data Science department?"]
    assert suggester.suggest("MECH lab") == ["What labs does the Mechanical Engineering department have?"]


def test_questions_starting_with_the_typed_text_come_first(tmp_path):
    suggester = make_suggester(tmp_path)
    assert suggester.suggest("how do")[0] == "How do I apply for admission?"
    assert len(suggester.suggest("what is the", limit=3)) == 3


def test_section_pages_are_suggested_by_title(services, tmp_path):
    suggester = Suggester.build(make_settings(tmp_path / "data", departments=[]), services.corpus)
    page_questions = [c.text for c in suggester.candidates if c.priority == 1]
    assert "Tell me about Facilities" in page_questions and "Tell me about the college" in page_questions
    assert len(suggester.candidates) == len(COMMON_QUESTIONS) + len(page_questions)


def test_suggest_endpoint(services):
    app = create_app(services.settings, services=services)
    with TestClient(app) as client:
        body = client.get("/api/suggest", params={"q": "bus"}).json()
        assert body == {"suggestions": ["Is college bus transport available?"]}
        assert client.get("/api/suggest", params={"q": "x" * 300}).json() == {"suggestions": []}
