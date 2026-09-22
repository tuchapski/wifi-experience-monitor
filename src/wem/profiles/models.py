from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SamplingConfig(ProfileModel):
    wifi_interval_seconds: float = Field(default=5.0, ge=1.0, le=3600.0)


class SyntheticTestConfig(ProfileModel):
    enabled: bool = True
    interval_seconds: float = Field(default=5.0, ge=1.0, le=86400.0)
    timeout_seconds: float | None = Field(default=None, gt=0.0, le=300.0)


class GatewayTestConfig(SyntheticTestConfig):
    automatic_gateway: bool = True
    target: str | None = Field(default=None, min_length=1, max_length=253)

    @model_validator(mode="after")
    def require_explicit_target(self) -> Self:
        if not self.automatic_gateway and self.target is None:
            raise ValueError("target is required when automatic_gateway is false")
        return self


class DNSTestConfig(SyntheticTestConfig):
    query: str = Field(default="example.com", min_length=1, max_length=253)


class InternetTestConfig(SyntheticTestConfig):
    target: str = Field(default="1.1.1.1", min_length=1, max_length=253)


class HTTPSTestConfig(SyntheticTestConfig):
    url: str = Field(default="https://example.com", max_length=2048)

    @field_validator("url")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be an absolute HTTP or HTTPS URL")
        return value


class TestConfigurations(ProfileModel):
    gateway: GatewayTestConfig = Field(
        default_factory=lambda: GatewayTestConfig(timeout_seconds=6.0)
    )
    dns: DNSTestConfig = Field(default_factory=DNSTestConfig)
    internet: InternetTestConfig = Field(
        default_factory=lambda: InternetTestConfig(timeout_seconds=6.0)
    )
    https: HTTPSTestConfig = Field(default_factory=lambda: HTTPSTestConfig(timeout_seconds=5.0))


class WifiThresholds(ProfileModel):
    rssi_warning_dbm: float = Field(default=-75.0, ge=-127.0, le=-1.0)
    rssi_critical_dbm: float = Field(default=-82.0, ge=-127.0, le=-1.0)
    retry_warning_percent: float = Field(default=20.0, ge=0.0, le=100.0)
    retry_critical_percent: float = Field(default=50.0, ge=0.0, le=100.0)
    tx_failure_critical_percent: float = Field(default=5.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_severity_order(self) -> Self:
        if self.rssi_critical_dbm >= self.rssi_warning_dbm:
            raise ValueError("rssi_critical_dbm must be lower than rssi_warning_dbm")
        if self.retry_critical_percent <= self.retry_warning_percent:
            raise ValueError("retry_critical_percent must exceed retry_warning_percent")
        return self


class LatencyLossThresholds(ProfileModel):
    latency_warning_ms: float = Field(gt=0.0)
    packet_loss_warning_percent: float = Field(default=5.0, ge=0.0, le=100.0)
    packet_loss_critical_percent: float = Field(default=20.0, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_loss_order(self) -> Self:
        if self.packet_loss_critical_percent <= self.packet_loss_warning_percent:
            raise ValueError("packet_loss_critical_percent must exceed packet_loss_warning_percent")
        return self


class LatencyThreshold(ProfileModel):
    latency_warning_ms: float = Field(gt=0.0)


class ResponseThreshold(ProfileModel):
    response_warning_ms: float = Field(gt=0.0)


class ProfileThresholds(ProfileModel):
    wifi: WifiThresholds = Field(default_factory=WifiThresholds)
    gateway: LatencyLossThresholds = Field(
        default_factory=lambda: LatencyLossThresholds(latency_warning_ms=50.0)
    )
    internet: LatencyLossThresholds = Field(
        default_factory=lambda: LatencyLossThresholds(latency_warning_ms=150.0)
    )
    dns: LatencyThreshold = Field(
        default_factory=lambda: LatencyThreshold(latency_warning_ms=250.0)
    )
    https: ResponseThreshold = Field(
        default_factory=lambda: ResponseThreshold(response_warning_ms=1000.0)
    )


class TestProfileConfig(ProfileModel):
    schema_version: Literal[1] = 1
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    tests: TestConfigurations = Field(default_factory=TestConfigurations)
    thresholds: ProfileThresholds = Field(default_factory=ProfileThresholds)

    @model_validator(mode="after")
    def validate_test_cadence(self) -> Self:
        wifi_interval = self.sampling.wifi_interval_seconds
        for name in ("gateway", "dns", "internet", "https"):
            test = getattr(self.tests, name)
            if not test.enabled:
                continue
            ratio = test.interval_seconds / wifi_interval
            if test.interval_seconds < wifi_interval or abs(ratio - round(ratio)) > 1e-9:
                raise ValueError(
                    f"enabled test {name} interval_seconds must be an integer "
                    "multiple of sampling.wifi_interval_seconds"
                )
        return self
