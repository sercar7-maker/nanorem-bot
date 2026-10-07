def require_ephemeral_test_database(database_url: str) -> None:
    if database_url != "sqlite://":
        raise RuntimeError(
            "Manual MLM test scripts require DATABASE_URL=sqlite:// "
            "to prevent changes to persistent databases"
        )
