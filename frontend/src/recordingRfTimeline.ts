import type { RfBssObservation, RfScanSnapshot } from "./agentTypes";

export const RECORDING_RF_STRONG_NEIGHBOR_DBM = -70;

export interface RecordingRfScanView {
  scan: RfScanSnapshot;
  associated: RfBssObservation | null;
  visibleSsids: number;
  sameSsid: number;
  strongNeighbors: number;
  bestSameSsidAlternative: RfBssObservation | null;
  alternativeDeltaDb: number | null;
  associatedChanged: boolean;
}

export interface RecordingRfTimelineSummary {
  scanCount: number;
  totalBssObservations: number;
  uniqueBss: number;
  uniqueSsids: number;
  associatedBssidChanges: number;
  associationCoveragePercent: number;
}

export interface RecordingRfTimelineData {
  summary: RecordingRfTimelineSummary;
  views: RecordingRfScanView[];
}

function normalizeBssid(value: string | null | undefined): string | null {
  return value?.trim().toLowerCase() || null;
}

function associatedBss(scan: RfScanSnapshot): RfBssObservation | null {
  const matches = scan.bsses.filter((bss) => bss.associated);
  return matches.length === 1 ? matches[0] : null;
}

export function buildRecordingRfTimeline(
  scans: RfScanSnapshot[],
): RecordingRfTimelineData {
  const ordered = [...scans].sort(
    (left, right) => Date.parse(left.observed_at) - Date.parse(right.observed_at),
  );
  const uniqueBss = new Set<string>();
  const uniqueSsids = new Set<string>();
  let totalBssObservations = 0;
  let scansWithAssociation = 0;
  let associatedBssidChanges = 0;
  let previousAssociatedBssid: string | null = null;
  let previousInterface: string | null = null;

  const views = ordered.map((scan) => {
    totalBssObservations += scan.bsses.length;
    for (const bss of scan.bsses) {
      uniqueBss.add(bss.bssid.toLowerCase());
      const ssid = bss.ssid?.trim();
      if (ssid) uniqueSsids.add(ssid);
    }

    const associated = associatedBss(scan);
    if (previousInterface !== scan.interface) previousAssociatedBssid = null;
    previousInterface = scan.interface;
    const associatedBssid = normalizeBssid(associated?.bssid);
    let associatedChanged = false;
    if (associatedBssid) {
      scansWithAssociation += 1;
      if (previousAssociatedBssid && previousAssociatedBssid !== associatedBssid) {
        associatedBssidChanges += 1;
        associatedChanged = true;
      }
      previousAssociatedBssid = associatedBssid;
    } else {
      previousAssociatedBssid = null;
    }

    const sameSsidBsses = associated?.ssid
      ? scan.bsses.filter((bss) => bss.ssid === associated.ssid)
      : [];
    const strongNeighbors = scan.bsses.filter((bss) => (
      normalizeBssid(bss.bssid) !== associatedBssid
      && bss.rssi_dbm != null
      && bss.rssi_dbm >= RECORDING_RF_STRONG_NEIGHBOR_DBM
    )).length;
    const alternatives = sameSsidBsses
      .filter((bss) => normalizeBssid(bss.bssid) !== associatedBssid)
      .filter((bss) => bss.rssi_dbm != null)
      .sort((left, right) => (right.rssi_dbm ?? -200) - (left.rssi_dbm ?? -200));
    const bestSameSsidAlternative = alternatives[0] ?? null;
    const alternativeDeltaDb = (
      associated?.rssi_dbm != null
      && bestSameSsidAlternative?.rssi_dbm != null
    )
      ? bestSameSsidAlternative.rssi_dbm - associated.rssi_dbm
      : null;

    return {
      scan,
      associated,
      visibleSsids: new Set(
        scan.bsses
          .map((bss) => bss.ssid?.trim())
          .filter((value): value is string => Boolean(value)),
      ).size,
      sameSsid: sameSsidBsses.length,
      strongNeighbors,
      bestSameSsidAlternative,
      alternativeDeltaDb,
      associatedChanged,
    };
  });

  return {
    summary: {
      scanCount: ordered.length,
      totalBssObservations,
      uniqueBss: uniqueBss.size,
      uniqueSsids: uniqueSsids.size,
      associatedBssidChanges,
      associationCoveragePercent: ordered.length === 0
        ? 0
        : (scansWithAssociation / ordered.length) * 100,
    },
    views,
  };
}
