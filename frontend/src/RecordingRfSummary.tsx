import type { RecordingRfSummary, RfSampleStatistics } from "./agentTypes";

function number(value: number | null | undefined, unit = ""): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const rendered = Number.isInteger(value) ? String(value) : value.toFixed(1);
  return unit ? `${rendered} ${unit}` : rendered;
}

function RfStatisticsCard({ label, stats, total, detail }: {
  label: string;
  stats: RfSampleStatistics;
  total: number;
  detail: string;
}) {
  return (
    <article>
      <span>{label}</span>
      <strong>{number(stats.average)}</strong>
      <small>Mean per valid scan · min {number(stats.minimum)} / max {number(stats.maximum)}</small>
      <small>{stats.sample_count}/{total} valid scans · {detail}</small>
    </article>
  );
}

export default function RfDerivedSummary({ summary }: { summary: RecordingRfSummary }) {
  const total = summary.scan_count;
  return (
    <div className="recording-rf-derived">
      <h3>Observed neighborhood summary</h3>
      <p>
        All {total.toLocaleString()} stored RF scans ·{" "}
        {summary.first_scan_at ? new Date(summary.first_scan_at).toLocaleString() : "—"} to{" "}
        {summary.last_scan_at ? new Date(summary.last_scan_at).toLocaleString() : "—"}.
        Counts refer to BSS, which may include several radios or SSIDs from one physical AP.
      </p>
      <p>
        {summary.unique_bss} unique BSS · {summary.unique_ssids} visible SSIDs ·{" "}
        {summary.total_bss_observations.toLocaleString()} BSS observations
      </p>
      <div className="recording-rf-derived-grid">
        <RfStatisticsCard label="Visible neighbors" stats={summary.visible_neighbors} total={total}
          detail="excludes BSS marked associated" />
        <RfStatisticsCard label="Same-channel neighbors" stats={summary.same_channel_neighbors}
          total={total} detail="same primary frequency; excludes associated BSS" />
        <RfStatisticsCard label="Same-SSID neighbors" stats={summary.same_ssid_neighbors}
          total={total} detail="exact SSID match; excludes associated BSS" />
        <RfStatisticsCard label={`Strong neighbors ≥ ${summary.strong_neighbor_threshold_dbm} dBm`}
          stats={summary.strong_neighbors} total={total} detail="requires all neighbor RSSI values" />
        <article>
          <span>Stronger same-SSID alternative</span>
          <strong>{number(summary.stronger_same_ssid_percent, "%")}</strong>
          <small>{summary.stronger_same_ssid_scan_count}/{summary.best_same_ssid_delta_db.sample_count}
            {" "}comparable scans · strictly higher RSSI</small>
          <small>Best alternative Δ: mean {number(summary.best_same_ssid_delta_db.average, "dB")},
            {" "}max {number(summary.best_same_ssid_delta_db.maximum, "dB")}</small>
          <small>Signal comparison; roaming suitability is not evaluated.</small>
        </article>
        <article>
          <span>Observed association changes</span>
          <strong>{summary.associated_bssid_changes} BSSID · {summary.associated_frequency_changes} frequency</strong>
          <small>{summary.association_transition_pairs} consecutive comparable scan pairs</small>
          <small>Missing or ambiguous association breaks continuity.</small>
        </article>
        <article>
          <span>Visible neighborhood changes</span>
          <strong>{summary.neighborhood_changed_pairs}/{summary.neighborhood_transition_pairs} pairs</strong>
          <small>{summary.visible_bss_additions} appearances · {summary.visible_bss_removals} disappearances</small>
          <small>Visibility between scans; AP installation or removal is not inferred.</small>
        </article>
        <article>
          <span>Evidence coverage</span>
          <strong>{number(summary.association_coverage_percent, "%")} association visible</strong>
          <small>{summary.scans_with_association}/{total} scans with one associated BSS</small>
          <small>Largest interval between scans: {number(summary.maximum_scan_gap_seconds, "s")}</small>
          <small>Statistics describe sampled scans, not time-weighted exposure.</small>
        </article>
      </div>
    </div>
  );
}
