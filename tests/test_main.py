"""Tests for __main__.py startup wiring."""

import os
import subprocess
import sys

import pytest


@pytest.fixture
def env_vars(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_vinyl.db")
    monkeypatch.setenv("DISCOGS_TOKEN", "test-token")
    monkeypatch.setenv("EBAY_APP_ID", "test-app-id")
    monkeypatch.setenv("EBAY_CERT_ID", "test-cert-id")
    monkeypatch.setenv("TELEGRAM_TOKEN", "test-telegram")
    monkeypatch.setenv("DB_PATH", db_path)
    return db_path


def test_main_startup_prints_message_and_exits_zero(tmp_path):
    db_path = str(tmp_path / "test_vinyl.db")
    env = os.environ.copy()
    env.update({
        "DISCOGS_TOKEN": "test-token",
        "EBAY_APP_ID": "test-app-id",
        "EBAY_CERT_ID": "test-cert-id",
        "TELEGRAM_TOKEN": "test-telegram",
        "DB_PATH": db_path,
    })
    result = subprocess.run(
        [sys.executable, "-m", "vinyl_detective"],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    assert result.returncode == 0
    assert "Vinyl Detective started" in result.stdout
    assert db_path in result.stdout


def test_main_creates_db_file(tmp_path):
    db_path = str(tmp_path / "test_vinyl.db")
    env = os.environ.copy()
    env.update({
        "DISCOGS_TOKEN": "test-token",
        "EBAY_APP_ID": "test-app-id",
        "EBAY_CERT_ID": "test-cert-id",
        "TELEGRAM_TOKEN": "test-telegram",
        "DB_PATH": db_path,
    })
    subprocess.run(
        [sys.executable, "-m", "vinyl_detective"],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    assert os.path.exists(db_path)


def test_main_fails_without_env_vars():
    env = os.environ.copy()
    for key in ("DISCOGS_TOKEN", "EBAY_APP_ID", "EBAY_CERT_ID", "TELEGRAM_TOKEN"):
        env.pop(key, None)
    result = subprocess.run(
        [sys.executable, "-m", "vinyl_detective"],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    assert result.returncode != 0
