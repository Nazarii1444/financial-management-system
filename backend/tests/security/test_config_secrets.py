"""APP_ENV=production refuses weak secrets; development only warns."""
import logging

import pytest

from src import config

STRONG = "x" * 48


@pytest.mark.parametrize("secret", ["", "secret_key", "change-me-in-production", "short-but-not-placeholder"])
def test_production_refuses_weak_secret_key(monkeypatch, secret):
    monkeypatch.setattr(config, "SECRET_KEY", secret)
    monkeypatch.setattr(config, "SESSION_SECRET", secret)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        config.check_secrets(production=True)


def test_production_refuses_weak_explicit_session_secret(monkeypatch):
    monkeypatch.setattr(config, "SECRET_KEY", STRONG)
    monkeypatch.setattr(config, "SESSION_SECRET", "super-session-secret")
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        config.check_secrets(production=True)


def test_production_accepts_strong_secrets(monkeypatch):
    monkeypatch.setattr(config, "SECRET_KEY", STRONG)
    monkeypatch.setattr(config, "SESSION_SECRET", STRONG)
    config.check_secrets(production=True)


def test_development_only_warns(monkeypatch, caplog):
    monkeypatch.setattr(config, "SECRET_KEY", "secret_key")
    monkeypatch.setattr(config, "SESSION_SECRET", "secret_key")
    with caplog.at_level(logging.WARNING, logger=config.logger.name):
        config.check_secrets(production=False)
    assert "SECRET_KEY" in caplog.text
