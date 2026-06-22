from config.settings import get_settings


def test_default_settings(monkeypatch):
    monkeypatch.delenv("HEADLESS_BROWSER", raising=False)
    monkeypatch.delenv("DOWNLOAD_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("MAX_RETRIES", raising=False)

    settings = get_settings()

    assert settings.headless_browser is True
    assert settings.download_timeout_seconds == 60
    assert settings.max_retries == 3
    assert settings.data_dir.name == "data"
    assert settings.raw_data_dir.name == "raw"
    assert settings.tmp_download_dir.name == "tmp"


def test_settings_env_overrides(monkeypatch):
    monkeypatch.setenv("HEADLESS_BROWSER", "false")
    monkeypatch.setenv("DOWNLOAD_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("MAX_RETRIES", "5")

    settings = get_settings()

    assert settings.headless_browser is False
    assert settings.download_timeout_seconds == 120
    assert settings.max_retries == 5