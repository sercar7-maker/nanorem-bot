import os
import subprocess
import sys
from pathlib import Path


def test_debug_configuration_does_not_print_database_credentials():
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["DEBUG"] = "true"
    environment["DATABASE_URL"] = (
        "postgresql://audit_user:do-not-print-this@localhost/auditdb"
    )
    environment["WEBHOOK_URL"] = (
        "https://example.invalid/hook?token=webhook-secret-canary"
    )

    result = subprocess.run(
        [sys.executable, "-c", "import config"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "DATABASE: configured (postgresql)" in result.stdout
    assert "do-not-print-this" not in result.stdout
    assert "do-not-print-this" not in result.stderr
    assert "webhook-secret-canary" not in result.stdout
    assert "webhook-secret-canary" not in result.stderr
