import pytest

from core.manual_test_guard import require_ephemeral_test_database


def test_manual_mlm_scripts_reject_persistent_database_urls():
    for database_url in (
        "sqlite:///nanorem.db",
        "postgresql://example.invalid/database",
    ):
        with pytest.raises(RuntimeError, match="require DATABASE_URL=sqlite://"):
            require_ephemeral_test_database(database_url)


def test_manual_mlm_scripts_allow_ephemeral_sqlite():
    require_ephemeral_test_database("sqlite://")
