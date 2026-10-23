from rag.eval.fact_eval import load_fact_cases, normalize


def test_normalize_ignores_markdown_quotes_and_dashes():
    assert normalize("**Dr. M. Sekar** – Principal’s message") == normalize("dr. m. sekar - principal's message")


def test_fact_cases_load_with_their_split(tmp_path):
    path = tmp_path / "facts.jsonl"
    path.write_text('// comment\n{"question": "bus", "facts": ["12 buses"], "split": "holdout"}\n', encoding="utf-8")
    [case] = load_fact_cases(path)
    assert (case.question, case.facts, case.split) == ("bus", ["12 buses"], "holdout")


def test_the_live_question_set_is_well_formed():
    from rag.config import BACKEND_DIR

    cases = load_fact_cases(BACKEND_DIR / "eval" / "facts_aaacet.jsonl")
    assert len(cases) == 60 and {c.split for c in cases} == {"tune", "holdout"}
    assert all(2 <= len(c.facts) <= 6 for c in cases)
