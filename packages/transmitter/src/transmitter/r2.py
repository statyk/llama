"""boto3 client for R2's S3 API (spec "Publisher (phase 1)"). Keys come from
the environment (the service's env file); the account id and bucket from
config. botocore's own retries are off -- the Uploader owns retry/backoff so
every attempt is counted against the daily PUT budget -- and checksums are
only sent when an operation requires them."""

import os

from transmitter.config import PublishConfig
from transmitter.errors import ConfigError


def error_code(exc: Exception) -> str | None:
    """The S3 error code a botocore exception carries (`NoSuchKey`,
    `AccessDenied`, ...), or None for anything else. The one helper every R2
    reader and writer uses (publish.Uploader, monitor.R2Reader, cloudstate)."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return response.get("Error", {}).get("Code")
    return None


def make_client(cfg: PublishConfig, *, connect_timeout: float = 10, read_timeout: float = 60):
    import boto3
    from botocore.config import Config

    key = os.environ.get("R2_ACCESS_KEY_ID")
    secret = os.environ.get("R2_SECRET_ACCESS_KEY")
    if not key or not secret:
        raise ConfigError("set R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY (the service's env file)")
    endpoint = cfg.endpoint_url or (
        f"https://{cfg.account_id}.r2.cloudflarestorage.com" if cfg.account_id else None)
    if endpoint is None:
        raise ConfigError("set [publish] account_id (or endpoint_url) in transmitter's config.toml")
    return boto3.client(
        "s3", endpoint_url=endpoint, region_name="auto",
        aws_access_key_id=key, aws_secret_access_key=secret,
        config=Config(retries={"total_max_attempts": 1, "mode": "standard"},
                      request_checksum_calculation="when_required",
                      response_checksum_validation="when_required",
                      connect_timeout=connect_timeout, read_timeout=read_timeout),
    )
