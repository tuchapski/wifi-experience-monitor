import type { RfBssObservation, RfScanSnapshot, WifiCurrentState } from "./agentTypes";

export const STRONG_NEIGHBOR_RSSI_DBM = -70;

export interface RfEnvironmentSummary {
  visibleBss: number;
  visibleSsids: number;
  sameSsid: number;
  sameChannel: number;
  strongNeighbors: number;
  associated: RfBssObservation | null;
  bestSameSsidAlternative: RfBssObservation | null;
  alternativeDeltaDb: number | null;
}

function normalizedBssid(value: string | null | undefined): string | null {
  return value?.trim().toLowerCase() || null;
}

function associatedBss(
  scan: RfScanSnapshot,
  wifi: WifiCurrentState | null | undefined,
): RfBssObservation | null {
  const currentBssid = normalizedBssid(wifi?.bssid);
  if (currentBssid) {
    const exact = scan.bsses.find(
      (bss) => normalizedBssid(bss.bssid) === currentBssid,
    );
    if (exact) return exact;
  }
  return scan.bsses.find((bss) => bss.associated) ?? null;
}

export function summarizeRfEnvironment(
  scan: RfScanSnapshot,
  wifi?: WifiCurrentState | null,
): RfEnvironmentSummary {
  const associated = associatedBss(scan, wifi);
  const ssid = associated?.ssid ?? wifi?.ssid ?? null;
  const channel = associated?.channel ?? wifi?.channel ?? null;
  const associatedId = normalizedBssid(associated?.bssid ?? wifi?.bssid);

  const sameSsidBsses = ssid
    ? scan.bsses.filter((bss) => bss.ssid === ssid)
    : [];
  const sameChannelBsses = channel == null
    ? []
    : scan.bsses.filter((bss) => bss.channel === channel);
  const strongNeighbors = scan.bsses.filter((bss) => (
    normalizedBssid(bss.bssid) !== associatedId
    && bss.rssi_dbm != null
    && bss.rssi_dbm >= STRONG_NEIGHBOR_RSSI_DBM
  ));

  const alternatives = sameSsidBsses
    .filter((bss) => normalizedBssid(bss.bssid) !== associatedId)
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
    visibleBss: scan.bsses.length,
    visibleSsids: new Set(
      scan.bsses
        .map((bss) => bss.ssid?.trim())
        .filter((value): value is string => Boolean(value)),
    ).size,
    sameSsid: sameSsidBsses.length,
    sameChannel: sameChannelBsses.length,
    strongNeighbors: strongNeighbors.length,
    associated,
    bestSameSsidAlternative,
    alternativeDeltaDb,
  };
}

export function rfBandLabel(band: RfBssObservation["band"]): string {
  if (band === "2.4ghz") return "2.4 GHz";
  if (band === "5ghz") return "5 GHz";
  if (band === "6ghz") return "6 GHz";
  return "Unknown band";
}
