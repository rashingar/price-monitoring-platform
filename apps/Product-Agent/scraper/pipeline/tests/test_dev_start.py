from __future__ import annotations

from pipeline.dev import start


def test_dev_start_dry_run_prints_product_agent_urls(capsys) -> None:
    exit_code = start.main(["--host", "127.0.0.1", "--port", "8765", "--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Product-Agent API" in output
    assert "API URL: http://127.0.0.1:8765" in output
    assert "Health URL: http://127.0.0.1:8765/api/health" in output
    assert "Docs URL: http://127.0.0.1:8765/docs" in output
    assert "Jobs URL: http://127.0.0.1:8765/api/jobs" in output
