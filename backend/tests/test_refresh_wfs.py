"""Tests for the connection-string parsing in the WFS refresh ETL."""

import pytest

from etl.refresh_wfs import parse_connection


def _dsn_dict(dsn: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in dsn.split())


@pytest.fixture(autouse=True)
def clear_db_env(monkeypatch):
    monkeypatch.delenv("IMPORT_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


class TestParseConnection:
    def test_basic_url_parsed_into_dsn(self, monkeypatch):
        monkeypatch.setenv("IMPORT_DATABASE_URL", "postgresql://bob:secret@db.example.com:5433/areas")
        dsn, pg = parse_connection()
        d = _dsn_dict(dsn)
        assert d["host"] == "db.example.com"
        assert d["port"] == "5433"
        assert d["dbname"] == "areas"
        assert d["user"] == "bob"
        assert d["password"] == "secret"
        assert d["sslmode"] == "prefer"
        assert pg == "PG:" + dsn

    def test_sqlalchemy_driver_suffix_is_stripped(self, monkeypatch):
        monkeypatch.setenv(
            "IMPORT_DATABASE_URL", "postgresql+asyncpg://u:p@h.example.com:5432/db"
        )
        dsn, _ = parse_connection()
        d = _dsn_dict(dsn)
        assert d["host"] == "h.example.com"
        assert d["user"] == "u"

    def test_neon_pooler_host_is_normalised_and_ssl_required(self, monkeypatch):
        monkeypatch.setenv(
            "IMPORT_DATABASE_URL",
            "postgresql://u:p@ep-cool-pooler.eu-central-1.aws.neon.tech:5432/db",
        )
        dsn, _ = parse_connection()
        d = _dsn_dict(dsn)
        assert d["host"] == "ep-cool.eu-central-1.aws.neon.tech"
        assert d["sslmode"] == "require"

    def test_url_encoded_password_is_unquoted(self, monkeypatch):
        monkeypatch.setenv("IMPORT_DATABASE_URL", "postgresql://u:p%40ss%21@h.example.com/db")
        dsn, _ = parse_connection()
        assert _dsn_dict(dsn)["password"] == "p@ss!"

    def test_defaults_to_port_5432(self, monkeypatch):
        monkeypatch.setenv("IMPORT_DATABASE_URL", "postgresql://u:p@h.example.com/db")
        assert _dsn_dict(parse_connection()[0])["port"] == "5432"

    def test_falls_back_to_database_url(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@fallback.example.com/db")
        assert _dsn_dict(parse_connection()[0])["host"] == "fallback.example.com"

    def test_missing_env_exits(self):
        with pytest.raises(SystemExit):
            parse_connection()
