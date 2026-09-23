import type {
  ApplicationTargetMetric,
  DiagnosticFinding,
  SensorSnapshot,
  TestOutcome,
} from "./types";


export type DashboardState = "healthy" | "warning" | "critical" | "unavailable";


export function outcomeDashboardState(outcome?: TestOutcome): DashboardState {
  if (!outcome) return "unavailable";
  if (outcome.status === "passed") return "healthy";
  if (outcome.status === "failed") return "critical";
  return "unavailable";
}


export function findingDashboardState(
  findings: DiagnosticFinding[] | undefined,
  matcher: (finding: DiagnosticFinding) => boolean,
  complete: boolean,
): DashboardState {
  const matching = (findings ?? []).filter(matcher);
  if (matching.some((finding) => finding.severity === "critical")) return "critical";
  if (matching.some((finding) => finding.severity === "warning")) return "warning";
  return complete ? "healthy" : "unavailable";
}


export function wifiDashboardState(snapshot: SensorSnapshot): DashboardState {
  if (snapshot.wifi.associated === false) return "critical";
  const findingState = findingDashboardState(
    snapshot.diagnostic?.findings,
    (finding) => finding.domain === "wifi",
    snapshot.diagnostic?.complete === true,
  );
  if (findingState === "critical" || findingState === "warning") return findingState;
  if (snapshot.wifi.associated === true && snapshot.diagnostic?.complete === true) return "healthy";
  return "unavailable";
}


export function applicationTargetDashboardState(
  target: ApplicationTargetMetric,
): DashboardState {
  if (target.status === "passed") return "healthy";
  if (target.status === "failed") return "critical";
  return "unavailable";
}


export function applicationsDashboardState(
  targets?: Record<string, ApplicationTargetMetric>,
): DashboardState {
  const active = Object.values(targets ?? {}).filter((target) => target.status !== "disabled");
  if (active.length === 0) return "unavailable";
  if (active.some((target) => target.status === "failed")) return "critical";

  const passed = active.filter((target) => target.status === "passed").length;
  const uncertain = active.length - passed;
  if (uncertain === 0) return "healthy";
  if (passed > 0) return "warning";
  return "unavailable";
}


export function overallDashboardState(snapshot: SensorSnapshot): DashboardState {
  const status = snapshot.diagnostic?.overall_status;
  if (status === "critical") return "critical";
  if (status === "warning") return "warning";
  if (
    status === "healthy"
    && snapshot.diagnostic?.complete === true
    && snapshot.collector_errors.length === 0
  ) {
    return "healthy";
  }
  return "unavailable";
}
