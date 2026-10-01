import type { RecordingRfScanWindow } from "./agentTypes";

export interface RfScanBand {
  scan: RecordingRfScanWindow;
  startFraction: number;
  endFraction: number;
}

export function buildRfScanBands(
  windows: RecordingRfScanWindow[],
  bounds: { start: number; end: number } | null,
): RfScanBand[] {
  if (!bounds || !Number.isFinite(bounds.start) || !Number.isFinite(bounds.end)
    || bounds.end <= bounds.start) return [];
  const bands: RfScanBand[] = [];
  const ids = new Set<string>();
  for (const scan of windows) {
    const start = Date.parse(scan.started_at);
    const end = Date.parse(scan.ended_at);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end < start
      || start > bounds.end || end < bounds.start || ids.has(scan.scan_id)) continue;
    ids.add(scan.scan_id);
    bands.push({
      scan,
      startFraction: (Math.max(bounds.start, start) - bounds.start) / (bounds.end - bounds.start),
      endFraction: (Math.min(bounds.end, end) - bounds.start) / (bounds.end - bounds.start),
    });
  }
  return bands.sort((left, right) => left.startFraction - right.startFraction);
}
