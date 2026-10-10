import pytest

from transmitter import r2
from transmitter.config import PublishConfig
from transmitter.errors import ConfigError


def test_client_needs_keys(monkeypatch):
    monkeypatch.delenv("R2_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("R2_SECRET_ACCESS_KEY", raising=False)
    with pytest.raises(ConfigError, match="R2_ACCESS_KEY_ID"):
        r2.make_client(PublishConfig(account_id="acct", bucket="b"))


def test_client_endpoint_from_account(monkeypatch):
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    client = r2.make_client(PublishConfig(account_id="acct", bucket="b"))
    assert client.meta.endpoint_url == "https://acct.r2.cloudflarestorage.com"
    # one HTTP request per Uploader attempt, so every attempt is counted against the PUT
    # budget (botocore reads a bare `max_attempts: 1` as one *retry*: 2 requests)
    assert client.meta.config.retries["total_max_attempts"] == 1
    override = r2.make_client(PublishConfig(endpoint_url="http://localhost:9000", bucket="b"))
    assert override.meta.endpoint_url == "http://localhost:9000"


def test_client_needs_an_endpoint(monkeypatch):
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    with pytest.raises(ConfigError, match="account_id"):
        r2.make_client(PublishConfig(bucket="b"))
