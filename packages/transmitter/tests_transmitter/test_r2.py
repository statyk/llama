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


def test_client_timeouts_are_keywords(monkeypatch):
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    cfg = PublishConfig(account_id="acct", bucket="b")
    c = r2.make_client(cfg).meta.config
    assert (c.connect_timeout, c.read_timeout) == (10, 60)
    c = r2.make_client(cfg, connect_timeout=5, read_timeout=10).meta.config
    assert (c.connect_timeout, c.read_timeout) == (5, 10)


def test_error_code_reads_a_botocore_style_response():
    class ClientError(Exception):
        def __init__(self, code):
            super().__init__(code)
            self.response = {"Error": {"Code": code}}

    assert r2.error_code(ClientError("NoSuchKey")) == "NoSuchKey"
    assert r2.error_code(OSError("down")) is None
    bare = Exception("x")
    bare.response = "not a dict"
    assert r2.error_code(bare) is None


def test_no_module_reaches_for_a_private_error_code_helper():
    # Both R2 readers (publish.Uploader and monitor.R2Reader) and cloudstate
    # share the one public helper, r2.error_code (Task 4b review, BM3).
    import pathlib

    import transmitter
    src = pathlib.Path(transmitter.__file__).parent
    offenders = [p.name for p in src.glob("*.py") if "_error_code" in p.read_text()]
    assert offenders == []
