import type { WifiCurrentState } from "./agentTypes";

export interface WifiConnectionPresentation {
  band: string;
  frequency: string;
  generation: string;
  ieee: string;
  shorthand: string;
  phy: string;
}

interface WifiStandard {
  generation: string;
  ieee: string;
  shorthand: string;
}

function normalizePhy(value: string | null | undefined): string | null {
  const normalized = value?.trim().toUpperCase();
  return normalized || null;
}

export function wifiBandLabel(frequencyMhz: number | null | undefined): string {
  if (frequencyMhz == null || !Number.isFinite(frequencyMhz)) return "—";
  if (frequencyMhz >= 2400 && frequencyMhz < 2500) return "2.4 GHz";
  if (frequencyMhz >= 4900 && frequencyMhz < 5925) return "5 GHz";
  if (frequencyMhz >= 5925 && frequencyMhz <= 7125) return "6 GHz";
  return `${frequencyMhz} MHz`;
}

function standardForPhy(
  phy: string | null,
  frequencyMhz: number | null | undefined,
): WifiStandard | null {
  if (!phy) return null;
  if (phy === "EHT") {
    return { generation: "Wi-Fi 7", ieee: "802.11be", shorthand: "be" };
  }
  if (phy === "HE") {
    return {
      generation: frequencyMhz != null && frequencyMhz >= 5925 ? "Wi-Fi 6E" : "Wi-Fi 6",
      ieee: "802.11ax",
      shorthand: "ax",
    };
  }
  if (phy === "VHT") {
    return { generation: "Wi-Fi 5", ieee: "802.11ac", shorthand: "ac" };
  }
  if (phy === "HT") {
    return { generation: "Wi-Fi 4", ieee: "802.11n", shorthand: "n" };
  }
  return null;
}

export function describeWifiConnection(
  wifi: WifiCurrentState | null | undefined,
): WifiConnectionPresentation {
  const frequencyMhz = wifi?.frequency_mhz;
  const txPhy = normalizePhy(wifi?.tx_phy);
  const rxPhy = normalizePhy(wifi?.rx_phy);
  const txStandard = standardForPhy(txPhy, frequencyMhz);
  const rxStandard = standardForPhy(rxPhy, frequencyMhz);
  const standard = txStandard ?? rxStandard;

  const sameStandard = txStandard && rxStandard
    ? txStandard.generation === rxStandard.generation
      && txStandard.ieee === rxStandard.ieee
    : true;

  const generation = txStandard && rxStandard && !sameStandard
    ? `TX ${txStandard.generation} / RX ${rxStandard.generation}`
    : standard?.generation ?? "Unavailable";

  const ieee = txStandard && rxStandard && !sameStandard
    ? `TX ${txStandard.ieee} / RX ${rxStandard.ieee}`
    : standard?.ieee ?? "PHY not reported";

  const shorthand = txStandard && rxStandard && !sameStandard
    ? `${txStandard.shorthand}/${rxStandard.shorthand}`
    : standard?.shorthand ?? "—";

  const phy = txPhy && rxPhy && txPhy !== rxPhy
    ? `TX ${txPhy} / RX ${rxPhy}`
    : txPhy ?? rxPhy ?? "—";

  return {
    band: wifiBandLabel(frequencyMhz),
    frequency: frequencyMhz == null ? "—" : `${frequencyMhz} MHz`,
    generation,
    ieee,
    shorthand,
    phy,
  };
}
