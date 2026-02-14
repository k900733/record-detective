"""Tests for __main__.py basic startup validation."""

import os
import subprocess
import sys


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
        timeout=10,
    )
    assert result.returncode != 0
