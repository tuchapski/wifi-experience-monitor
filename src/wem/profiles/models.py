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


class ApplicationTargetConfig(SyntheticTestConfig):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["http", "tcp", "dns"]
    target: str = Field(min_length=1, max_length=2048)
    port: int | None = Field(default=None, ge=1, le=65535)

    @field_validator("name", "target")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if self.kind == "http":
            parsed = urlsplit(self.target)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("HTTP application target must be an absolute HTTP or HTTPS URL")
            if self.port is not None:
                raise ValueError("HTTP application target port must be omitted; use the URL port")
        elif self.kind == "tcp":
            if "://" in self.target:
                raise ValueError("TCP application target must be a host name or IP address")
            if self.port is None:
                raise ValueError("TCP application target requires a port")
        elif self.port is not None:
            raise ValueError("DNS application target does not use a port")
        return self


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


class ConnectionStageP95Threshold(ProfileModel):
    p95_warning_ms: float = Field(gt=0.0, le=300000.0)
    p95_critical_ms: float = Field(gt=0.0, le=300000.0)

    @model_validator(mode="after")
    def validate_stage_slo(self) -> Self:
        if self.p95_critical_ms <= self.p95_warning_ms:
            raise ValueError("stage p95_critical_ms must exceed p95_warning_ms")
        return self


class ConnectionCycleStageThresholds(ProfileModel):
    association: ConnectionStageP95Threshold = Field(
        default_factory=lambda: ConnectionStageP95Threshold(
            p95_warning_ms=1500.0,
            p95_critical_ms=3000.0,
        )
    )
    authentication: ConnectionStageP95Threshold = Field(
        default_factory=lambda: ConnectionStageP95Threshold(
            p95_warning_ms=3000.0,
            p95_critical_ms=6000.0,
        )
    )
    ipv4: ConnectionStageP95Threshold = Field(
        default_factory=lambda: ConnectionStageP95Threshold(
            p95_warning_ms=5000.0,
            p95_critical_ms=10000.0,
        )
    )
    gateway: ConnectionStageP95Threshold = Field(
        default_factory=lambda: ConnectionStageP95Threshold(
            p95_warning_ms=6000.0,
            p95_critical_ms=12000.0,
        )
    )
    dns: ConnectionStageP95Threshold = Field(
        default_factory=lambda: ConnectionStageP95Threshold(
            p95_warning_ms=7000.0,
            p95_critical_ms=14000.0,
        )
    )


class ConnectionCycleThresholds(ProfileModel):
    window_size: int = Field(default=20, ge=3, le=200)
    minimum_samples: int = Field(default=5, ge=3, le=200)
    p95_warning_ms: float = Field(default=8000.0, gt=0.0, le=300000.0)
    p95_critical_ms: float = Field(default=15000.0, gt=0.0, le=300000.0)
    stages: ConnectionCycleStageThresholds = Field(default_factory=ConnectionCycleStageThresholds)

    @model_validator(mode="after")
    def validate_slo(self) -> Self:
        if self.minimum_samples > self.window_size:
            raise ValueError("minimum_samples must not exceed window_size")
        if self.p95_critical_ms <= self.p95_warning_ms:
            raise ValueError("p95_critical_ms must exceed p95_warning_ms")
        return self


class AdaptiveBaselineThresholds(ProfileModel):
    enabled: bool = True
    lookback_hours: int = Field(default=24, ge=1, le=168)
    minimum_samples: int = Field(default=30, ge=10, le=5000)
    max_samples: int = Field(default=1000, ge=30, le=10000)
    warning_sigma: float = Field(default=3.5, gt=0.0, le=20.0)
    critical_sigma: float = Field(default=6.0, gt=0.0, le=30.0)

    @model_validator(mode="after")
    def validate_baseline(self) -> Self:
        if self.max_samples < self.minimum_samples:
            raise ValueError("max_samples must be greater than or equal to minimum_samples")
        if self.critical_sigma <= self.warning_sigma:
            raise ValueError("critical_sigma must exceed warning_sigma")
        return self


class ServiceSloTarget(ProfileModel):
    availability_warning_percent: float = Field(default=99.0, ge=0.0, le=100.0)
    availability_critical_percent: float = Field(default=95.0, ge=0.0, le=100.0)
    latency_p95_warning_ms: float = Field(gt=0.0, le=300000.0)
    latency_p95_critical_ms: float = Field(gt=0.0, le=300000.0)
    packet_loss_p95_warning_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    packet_loss_p95_critical_percent: float | None = Field(default=None, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_service_slo_target(self) -> Self:
        if self.availability_critical_percent >= self.availability_warning_percent:
            raise ValueError(
                "availability_critical_percent must be lower than availability_warning_percent"
            )
        if self.latency_p95_critical_ms <= self.latency_p95_warning_ms:
            raise ValueError("latency_p95_critical_ms must exceed latency_p95_warning_ms")
        warning_loss = self.packet_loss_p95_warning_percent
        critical_loss = self.packet_loss_p95_critical_percent
        if (warning_loss is None) != (critical_loss is None):
            raise ValueError("packet-loss P95 warning and critical thresholds must both be set")
        if warning_loss is not None and critical_loss is not None and critical_loss <= warning_loss:
            raise ValueError(
                "packet_loss_p95_critical_percent must exceed packet_loss_p95_warning_percent"
            )
        return self


class ServiceSloThresholds(ProfileModel):
    enabled: bool = True
    window_size: int = Field(default=60, ge=10, le=1000)
    minimum_samples: int = Field(default=20, ge=5, le=1000)
    gateway: ServiceSloTarget = Field(
        default_factory=lambda: ServiceSloTarget(
            latency_p95_warning_ms=50.0,
            latency_p95_critical_ms=100.0,
            packet_loss_p95_warning_percent=5.0,
            packet_loss_p95_critical_percent=20.0,
        )
    )
    internet: ServiceSloTarget = Field(
        default_factory=lambda: ServiceSloTarget(
            latency_p95_warning_ms=150.0,
            latency_p95_critical_ms=300.0,
            packet_loss_p95_warning_percent=5.0,
            packet_loss_p95_critical_percent=20.0,
        )
    )
    dns: ServiceSloTarget = Field(
        default_factory=lambda: ServiceSloTarget(
            latency_p95_warning_ms=250.0,
            latency_p95_critical_ms=500.0,
        )
    )
    https: ServiceSloTarget = Field(
        default_factory=lambda: ServiceSloTarget(
            latency_p95_warning_ms=1000.0,
            latency_p95_critical_ms=2000.0,
        )
    )

    @model_validator(mode="after")
    def validate_service_slo_window(self) -> Self:
        if self.minimum_samples > self.window_size:
            raise ValueError("service SLO minimum_samples must not exceed window_size")
        return self


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
    connection_cycle: ConnectionCycleThresholds = Field(default_factory=ConnectionCycleThresholds)
    adaptive_baseline: AdaptiveBaselineThresholds = Field(
        default_factory=AdaptiveBaselineThresholds
    )
    service_slo: ServiceSloThresholds = Field(default_factory=ServiceSloThresholds)


class TestProfileConfig(ProfileModel):
    schema_version: Literal[1] = 1
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    tests: TestConfigurations = Field(default_factory=TestConfigurations)
    application_targets: list[ApplicationTargetConfig] = Field(default_factory=list, max_length=20)
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
        names: set[str] = set()
        for target in self.application_targets:
            normalized_name = target.name.casefold()
            if normalized_name in names:
                raise ValueError("application target names must be unique")
            names.add(normalized_name)
            if not target.enabled:
                continue
            ratio = target.interval_seconds / wifi_interval
            if target.interval_seconds < wifi_interval or abs(ratio - round(ratio)) > 1e-9:
                raise ValueError(
                    f"enabled application target {target.name} interval_seconds must be an "
                    "integer multiple of sampling.wifi_interval_seconds"
                )
        return self
