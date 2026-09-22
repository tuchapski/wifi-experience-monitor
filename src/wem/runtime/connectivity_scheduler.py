from copy import deepcopy
from dataclasses import dataclass

from wem.models.metrics import ConnectivityMetrics, TestOutcome
from wem.profiles.models import TestConfigurations
from wem.tests_engine.connectivity import ConnectivityTester

TEST_NAMES = ("gateway", "dns", "internet", "https")
TEST_DOMAINS = {
    "gateway": "gateway",
    "dns": "dns",
    "internet": "internet",
    "https": "application",
}
TEST_FIELDS = {
    "gateway": (
        "gateway_reachable",
        "gateway_packet_loss_percent",
        "gateway_latency_min_ms",
        "gateway_latency_avg_ms",
        "gateway_latency_max_ms",
        "gateway_jitter_ms",
    ),
    "dns": ("dns_success", "dns_latency_ms", "dns_query", "dns_result"),
    "internet": (
        "internet_reachable",
        "internet_packet_loss_percent",
        "internet_latency_min_ms",
        "internet_latency_avg_ms",
        "internet_latency_max_ms",
        "internet_jitter_ms",
    ),
    "https": ("https_success", "https_status_code", "https_total_time_ms"),
}


@dataclass(slots=True)
class ScheduledConnectivity:
    metrics: ConnectivityMetrics
    fresh_domains: set[str]


class ConnectivityTestScheduler:
    def __init__(self, tests: TestConfigurations) -> None:
        self.tests = tests.model_copy(deep=True)
        self._last_run: dict[str, float] = {}
        self._observed_monotonic: dict[str, float] = {}
        self._cache: dict[str, ConnectivityMetrics] = {}
        self._last_blocked: bool | None = None
        self._last_gateway: str | None = None

    def collect(
        self,
        tester: ConnectivityTester,
        *,
        now: float,
        observed_at: str,
        blocked: bool,
        gateway: str | None,
    ) -> ScheduledConnectivity:
        combined = ConnectivityMetrics()
        fresh_domains: set[str] = set()
        state_changed = self._last_blocked is not None and blocked != self._last_blocked
        gateway_changed = self._last_blocked is not None and gateway != self._last_gateway

        for name in TEST_NAMES:
            config = getattr(self.tests, name)
            if not config.enabled:
                combined.tests[name] = TestOutcome(
                    "disabled", "Test disabled by profile.", fresh=False, age_seconds=None
                )
                continue

            due = (
                name not in self._last_run
                or now - self._last_run[name] >= config.interval_seconds
                or state_changed
                or (name == "gateway" and gateway_changed)
            )
            if due:
                partial = self._blocked_result(name) if blocked else tester.run_test(name)
                outcome = partial.tests[name]
                outcome.observed_at = observed_at
                outcome.fresh = True
                outcome.age_seconds = 0.0
                self._cache[name] = deepcopy(partial)
                self._last_run[name] = now
                self._observed_monotonic[name] = now
                if outcome.status in {"passed", "failed"}:
                    fresh_domains.add(TEST_DOMAINS[name])

            cached = deepcopy(self._cache[name])
            cached_outcome = cached.tests[name]
            if not due:
                cached_outcome.fresh = False
                cached_outcome.age_seconds = round(
                    max(0.0, now - self._observed_monotonic[name]), 3
                )
            self._merge(combined, name, cached)

        self._last_blocked = blocked
        self._last_gateway = gateway
        return ScheduledConnectivity(combined, fresh_domains)

    @staticmethod
    def _blocked_result(name: str) -> ConnectivityMetrics:
        scope = "host" if name in {"dns", "https"} else "selected_interface"
        return ConnectivityMetrics(
            tests={
                name: TestOutcome(
                    "skipped",
                    "Interface unavailable, unverified, blocked or disconnected.",
                    scope,
                )
            }
        )

    @staticmethod
    def _merge(
        combined: ConnectivityMetrics,
        name: str,
        partial: ConnectivityMetrics,
    ) -> None:
        combined.tests[name] = partial.tests[name]
        for field_name in TEST_FIELDS[name]:
            setattr(combined, field_name, getattr(partial, field_name))
