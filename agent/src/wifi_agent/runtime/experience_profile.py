"""Apply Server policy at a probe boundary, with a last-applied local copy."""

import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from wifi_agent.config import AgentSettings
from wifi_agent.runtime.synthetic import SyntheticProbeRuntime
from wifi_agent.storage import AgentIdentity


@dataclass(frozen=True, slots=True)
class RuntimeExperienceProfile:
    version: str
    enabled: bool
    dns_query: str
    internet_target: str
    https_url: str
    interval_seconds: float
    timeout_seconds: float
    raw: dict

    @classmethod
    def parse(cls, payload: dict) -> "RuntimeExperienceProfile":
        version = payload.get("version")
        profile = payload.get("profile")
        if (
            not isinstance(version, str)
            or not re.fullmatch(r"exp_[0-9a-f]{32}", version)
            or not isinstance(profile, dict)
        ):
            raise ValueError("Invalid experience profile version or payload")
        enabled = profile.get("enabled")
        if type(enabled) is not bool:
            raise ValueError("Profile enabled must be boolean")
        targets = [profile.get("dns_query"), profile.get("internet_target")]
        for target in targets:
            if (
                not isinstance(target, str)
                or len(target) > 253
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:\-]*", target)
            ):
                raise ValueError("Invalid probe target")
        url = profile.get("https_url")
        if not isinstance(url, str) or len(url) > 2048:
            raise ValueError("Invalid HTTPS URL")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or any(c.isspace() for c in url)
        ):
            raise ValueError("Invalid HTTPS URL")
        _ = parsed.port
        interval, timeout = profile.get("interval_seconds"), profile.get("timeout_seconds")
        for value, lower, upper in ((interval, 5, 20), (timeout, 1, 10)):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not lower <= value <= upper
            ):
                raise ValueError("Probe cadence or timeout outside supported range")
        if type(profile.get("automatic_capture", False)) is not bool:
            raise ValueError("Automatic capture must be boolean")
        for key, lower, upper, default in (
            ("capture_pre_seconds", 0, 300, 120),
            ("capture_post_seconds", 30, 900, 300),
            ("capture_cooldown_seconds", 30, 3600, 300),
        ):
            value = profile.get(key, default)
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError("Capture window outside supported range")
        return cls(
            version,
            enabled,
            targets[0],
            targets[1],
            url,
            float(interval),
            float(timeout),
            deepcopy(payload),
        )


class ExperienceProfileRuntime:
    def __init__(self, settings: AgentSettings, identity: AgentIdentity):
        self.settings = settings
        self.identity = identity
        self.path: Path = settings.data_dir / "experience-profile.json"
        self.active: RuntimeExperienceProfile | None = None
        self.pending: RuntimeExperienceProfile | None = None
        if self.path.exists():
            saved = json.loads(self.path.read_text())
            if not isinstance(saved, dict):
                raise ValueError("Saved experience profile must be an object")
            if (
                saved.get("agent_id") == identity.agent_id
                and saved.get("server_url") == identity.server_url
            ):
                self.active = RuntimeExperienceProfile.parse(saved["payload"])

    @property
    def version(self) -> str | None:
        return self.active.version if self.active else None

    @property
    def interval_seconds(self) -> float:
        return (
            self.active.interval_seconds
            if self.active and self.active.enabled
            else self.settings.synthetic_probe_interval_seconds
        )

    @property
    def timeout_seconds(self) -> float:
        return (
            self.active.timeout_seconds
            if self.active and self.active.enabled
            else self.settings.synthetic_probe_timeout_seconds
        )

    def receive(self, payload: dict | None) -> None:
        if payload is None:
            return
        profile = RuntimeExperienceProfile.parse(payload)
        if self.active is None or profile.version != self.active.version:
            self.pending = profile

    def apply(self) -> bool:
        if self.pending is None:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "agent_id": self.identity.agent_id,
                    "server_url": self.identity.server_url,
                    "payload": self.pending.raw,
                }
            )
        )
        temporary.replace(self.path)
        self.active, self.pending = self.pending, None
        return True

    def make_probes(self, interface: str) -> SyntheticProbeRuntime:
        active = self.active if self.active and self.active.enabled else None
        return SyntheticProbeRuntime(
            interface,
            dns_query=active.dns_query if active else self.settings.dns_probe_query,
            internet_target=active.internet_target
            if active
            else self.settings.internet_probe_target,
            https_url=active.https_url if active else self.settings.https_probe_url,
            timeout_seconds=self.timeout_seconds,
            profile_version=self.version,
            interval_seconds=self.interval_seconds,
        )
