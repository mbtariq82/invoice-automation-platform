from alembic import command
from alembic.config import Config


def test_offline_migration_accepts_url_encoded_password(monkeypatch, capsys) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://invoice_app:p%40ss%25word@/invoices"
        "?host=/cloudsql/example-project:europe-west2:invoice-dev-postgres",
    )

    command.upgrade(Config("alembic.ini"), "head", sql=True)

    assert "CREATE TABLE invoice_records" in capsys.readouterr().out
