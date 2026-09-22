from wem.models.metrics import ConnectivityMetrics
from wem.models.metrics import TestOutcome as Outcome
from wem.profiles.models import TestConfigurations as ConnectivityConfigurations
from wem.runtime.connectivity_scheduler import ConnectivityTestScheduler


class FakeTester:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run_test(self, name: str) -> ConnectivityMetrics:
        self.calls.append(name)
        metrics = ConnectivityMetrics(tests={name: Outcome("failed", f"{name} failed")})
        if name == "gateway":
            metrics.gateway_reachable = False
        elif name == "dns":
            metrics.dns_success = False
        elif name == "internet":
            metrics.internet_reachable = False
        else:
            metrics.https_success = False
        return metrics


def test_each_test_uses_its_own_interval_and_cached_results_are_stale() -> None:
    tests = ConnectivityConfigurations()
    tests.dns.interval_seconds = 10
    scheduler = ConnectivityTestScheduler(tests)
    tester = FakeTester()

    first = scheduler.collect(
        tester, now=0, observed_at="2026-09-22T10:00:00+00:00", blocked=False, gateway="gw"
    )
    second = scheduler.collect(
        tester, now=5, observed_at="2026-09-22T10:00:05+00:00", blocked=False, gateway="gw"
    )
    third = scheduler.collect(
        tester, now=10, observed_at="2026-09-22T10:00:10+00:00", blocked=False, gateway="gw"
    )

    assert first.metrics.tests["dns"].fresh is True
    assert "dns" in first.fresh_domains
    assert second.metrics.tests["dns"].fresh is False
    assert second.metrics.tests["dns"].age_seconds == 5
    assert "dns" not in second.fresh_domains
    assert third.metrics.tests["dns"].fresh is True
    assert tester.calls.count("dns") == 2
    assert tester.calls.count("gateway") == 3


def test_disabled_test_is_never_executed() -> None:
    tests = ConnectivityConfigurations()
    tests.https.enabled = False
    scheduler = ConnectivityTestScheduler(tests)
    tester = FakeTester()

    result = scheduler.collect(
        tester, now=0, observed_at="2026-09-22T10:00:00+00:00", blocked=False, gateway="gw"
    )

    assert "https" not in tester.calls
    assert result.metrics.tests["https"].status == "disabled"
    assert result.metrics.tests["https"].fresh is False
    assert "application" not in result.fresh_domains
