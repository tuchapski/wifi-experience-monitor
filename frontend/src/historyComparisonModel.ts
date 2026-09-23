import type { HistoryComparison, HistoryWindow } from "./types";

export function compareHistoryWindows(
  current: HistoryWindow,
  reference: HistoryWindow,
): HistoryComparison | null {
  if (current.interface !== reference.interface || !current.summary || !reference.summary) return null;
  return {
    current: current.summary,
    previous: reference.summary,
    previous_start: reference.start,
    previous_end: reference.end,
    connection_cycles: current.connection_cycle_summary && reference.connection_cycle_summary
      ? { current: current.connection_cycle_summary, previous: reference.connection_cycle_summary }
      : undefined,
    service_slo: current.service_slo_summary && reference.service_slo_summary
      ? { current: current.service_slo_summary, previous: reference.service_slo_summary }
      : undefined,
    application_availability: current.application_availability && reference.application_availability
      ? { current: current.application_availability, previous: reference.application_availability }
      : undefined,
  };
}
