from unittest import mock

from rag.config import PROJECT_DIR


def test_demo_never_touches_the_real_data_or_qdrant_cloud(settings, monkeypatch):
    from rag import cli

    real = settings.model_copy(update={"data_dir": PROJECT_DIR / "data", "qdrant_url": "https://cluster.cloud.qdrant.io:6333",
                                       "qdrant_api_key": "secret"})
    monkeypatch.setattr(cli, "get_settings", lambda: real)
    with mock.patch("rag.demo.site.build_demo_site", return_value=settings.data_dir), \
         mock.patch("rag.demo.site.serve_directory", return_value=(mock.Mock(), "http://127.0.0.1:1")), \
         mock.patch("rag.pipeline.run_pipeline", return_value={}) as run:
        assert cli.main(["demo"]) == 0
    used = run.call_args.args[0]
    assert used.data_dir == PROJECT_DIR / "data" / "demo"
    assert used.qdrant_url == "" and used.qdrant_api_key == ""
    assert real.qdrant_url.startswith("https://")  # the caller's settings are not changed
