import os

import pytest

from truth_backend.local_config import load_local_config


def test_local_config_preserves_process_values_and_never_expands(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "environ", {"TRUTH_AI_MODEL": "process-model"})
    (tmp_path / ".env").write_text('# local\nTRUTH_AI_MODEL=file-model\nTRUTH_AI_API_KEY="literal-$(command)-$HOME-#value"\nTRUTH_SEARCH_PROVIDER=deepseek\n', encoding="utf-8")
    load_local_config(tmp_path)
    assert os.environ["TRUTH_AI_MODEL"] == "process-model"
    assert os.environ["TRUTH_AI_API_KEY"] == "literal-$(command)-$HOME-#value"
    assert os.environ["TRUTH_SEARCH_PROVIDER"] == "deepseek"


@pytest.mark.parametrize("content", ["PYTHONPATH=PRIVATE_SECRET", "TRUTH_AI_API_KEY='PRIVATE_SECRET", "PRIVATE_SECRET"])
def test_invalid_local_config_does_not_echo_values_or_partially_apply(tmp_path, monkeypatch, content):
    monkeypatch.setattr(os, "environ", {})
    (tmp_path / ".env").write_text("TRUTH_AI_MODEL=not-applied\n" + content, encoding="utf-8")
    with pytest.raises(ValueError) as error:
        load_local_config(tmp_path)
    assert "PRIVATE_SECRET" not in str(error.value)
    assert "TRUTH_AI_MODEL" not in os.environ


def test_local_config_ignores_other_directory_and_rejects_oversized_files(tmp_path):
    load_local_config(tmp_path / "absent")
    (tmp_path / ".env").write_bytes(b"a" * 32769)
    with pytest.raises(ValueError, match="32 KB"):
        load_local_config(tmp_path)


@pytest.mark.parametrize("language", ["zh-CN", "en", "ja"])
def test_health_announces_default_native_search_without_returning_key(monkeypatch, language):
    from fastapi.testclient import TestClient
    import app
    monkeypatch.setenv("TRUTH_AI_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("TRUTH_AI_API_KEY", "HEALTH_TEST_SECRET")
    monkeypatch.setenv("TRUTH_SEARCH_PROVIDER", "deepseek")
    with TestClient(app.app, base_url="http://127.0.0.1") as client:
        response = client.get(f"/api/health?language={language}")
    assert response.status_code == 200
    data = response.json()
    assert data["configured"]["deepseek"] is True
    assert data["default_search_provider"] == "deepseek"
    assert "deepseek" in data["search_providers"]
    assert "HEALTH_TEST_SECRET" not in response.text
