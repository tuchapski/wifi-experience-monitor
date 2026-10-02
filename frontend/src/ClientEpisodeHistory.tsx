import { useEffect, useState } from "react";
import { acknowledgeClientEpisode, getClientEpisode, getClientEpisodes } from "./agentApi";
import type { ClientEpisode, ClientEpisodePage } from "./agentTypes";
import { clientEpisodeHash, diagnosticsRecordingHash } from "./diagnosticRoutes";
import "./ClientEpisodeHistory.css";
import { episodeStatus } from "./clientEpisodePresentation";

const DOMAINS: Record<string, string> = { wifi_rf: "Wi-Fi association", local_network: "Local network", dns: "DNS", internet: "Internet", application: "Application" };
const date = (time: string | null) => time ? new Date(time).toLocaleString() : "—";
function summary(episode: ClientEpisode, now: number) {
  return <><span className={`episode-status episode-${episodeStatus(episode, now)}`}>{episodeStatus(episode, now)}</span>
    {episode.evidence_gap && <span className="episode-gap">Evidence gap</span>}
    {episode.acknowledged_at && <span>Acknowledged</span>}</>;
}
export default function ClientEpisodeHistory({ agentId }: { agentId: string }) {
  const [page, setPage] = useState<ClientEpisodePage | null>(null);
  const [offset, setOffset] = useState(0);
  const [domain, setDomain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    let live = true;
    const load = () => void getClientEpisodes(agentId, offset, domain).then(data => {
      if (live) { setPage(data); setError(null); }
    }).catch(err => { if (live) { setPage(null); setError(err instanceof Error ? err.message : "Unable to load episodes"); } });
    load(); const poll = setInterval(load, 5000);
    return () => { live = false; clearInterval(poll); };
  }, [agentId, offset, domain]);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  return <section className="episode-panel" aria-label="Client episode history"><header><div><h2>Client episodes</h2><p>Confirmed findings for this client, with recovery and saved evidence.</p></div>
    <label>Domain<select value={domain} onChange={event => { setDomain(event.target.value); setOffset(0); }}><option value="">All domains</option>{Object.entries(DOMAINS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label></header>
    {error && <p role="alert" className="agent-error">{error}</p>}
    {!page && !error && <p>Loading episodes…</p>}
    {page?.total === 0 && <p>No confirmed episodes recorded. Enable continuous detection to start this history.</p>}
    <div className="episode-list">{page?.episodes.map(episode => <a className="episode-card" key={episode.id} href={clientEpisodeHash(agentId, episode.id)}>
      <div><strong>{DOMAINS[episode.domain] ?? episode.domain}</strong>{summary(episode, now)}</div>
      <span>{date(episode.started_at)} · {episode.target ?? episode.context.interface ?? "Association"}</span>
      <p>{episodeStatus(episode, now) === "unknown" ? "Fresh evidence unavailable; recovery unconfirmed." : episode.reason}</p>
      <small>{Math.round(episode.observed_duration_seconds)}s of observed degradation · {episode.capture ? `Capture ${episode.capture.status}` : "Automatic capture disabled"}{episode.recurrence_count ? ` · ${episode.recurrence_count} recurrence(s)` : ""}</small>
    </a>)}</div>
    {page && page.total > 0 && <footer><span>{offset + 1}–{Math.min(offset + 10, page.total)} of {page.total}</span><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 10))}>Previous</button><button disabled={offset + 10 >= page.total} onClick={() => setOffset(offset + 10)}>Next</button></footer>}
  </section>;
}
export function ClientEpisodeDetail({ agentId, episodeId }: { agentId: string; episodeId: string }) {
  const [episode, setEpisode] = useState<ClientEpisode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    let live = true;
    const load = () => void getClientEpisode(agentId, episodeId).then(data => { if (live) { setEpisode(data); setError(null); } }).catch(err => { if (live) { setEpisode(null); setError(err instanceof Error ? err.message : "Unable to load episode"); } });
    load(); const timer = setInterval(load, 5000);
    return () => { live = false; clearInterval(timer); };
  }, [agentId, episodeId]);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  async function acknowledge() {
    setBusy(true);
    try { await acknowledgeClientEpisode(agentId, episodeId); setEpisode(await getClientEpisode(agentId, episodeId)); setError(null); }
    catch (err) { setError(err instanceof Error ? err.message : "Acknowledgment failed"); }
    finally { setBusy(false); }
  }
  return <section className="episode-panel episode-detail"><a href={`#agents/${encodeURIComponent(agentId)}`}>← Back to client</a>
    {error && <p role="alert" className="agent-error">{error}</p>}
    {!episode && !error && <p>Loading episode…</p>}
    {episode && <><header><div><h1>{DOMAINS[episode.domain] ?? episode.domain} episode</h1><div>{summary(episode, now)}</div></div><button disabled={busy || !!episode.acknowledged_at} onClick={() => void acknowledge()}>{episode.acknowledged_at ? "Acknowledged" : busy ? "Saving…" : "Acknowledge"}</button></header>
      <p>{episodeStatus(episode, now) === "unknown" ? "Fresh evidence unavailable; recovery unconfirmed." : episode.reason}</p><p>Acknowledgment records review. Recovery requires new successful observations.</p>
      <dl className="episode-context">{[["Started", date(episode.started_at)], ["Confirmed", date(episode.confirmed_at)], ["Last observation", date(episode.last_observed_at)], ["Recovered", date(episode.recovered_at)], ["Observed degradation", `${Math.round(episode.observed_duration_seconds)}s`], ["Recurrences", String(episode.recurrence_count)], ...Object.entries(episode.context), ["Profile version", episode.profile_version], ["Detector", episode.detector_version]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || "—"}</dd></div>)}</dl>
      <h2>At confirmation</h2><div className="episode-findings">{episode.opening_findings?.map(finding => <article key={finding.rule_id}><strong>{finding.label}</strong><p>{String(finding.value ?? "Unknown")} {finding.unit} · {finding.reason}</p><small>Objective: {finding.objective ?? "—"} · Reference limit: {finding.baseline.upper_limit ?? "—"} · {date(finding.observed_at)}</small></article>)}</div>
      <h2>Latest findings and references</h2><div className="episode-findings">{episode.findings.map(finding => <article key={finding.rule_id}><strong>{finding.label}</strong><p>{finding.kind} · {finding.status} · {String(finding.value ?? "Unknown")} {finding.unit}</p><p>{finding.reason}</p><small>Objective: {finding.objective ?? "—"} · Reference: {finding.baseline.status}; {finding.baseline.samples} samples · median {finding.baseline.median ?? "—"}; p95 {finding.baseline.p95 ?? "—"}; limit {finding.baseline.upper_limit ?? "—"}</small></article>)}</div>
      <h2>Capture coverage</h2>{episode.capture ? <><p>{episode.capture.mode} · {episode.capture.status} · Requested {date(episode.capture.requested_start)} → {date(episode.capture.requested_end)}</p>
        {episode.capture.recording_id && <a href={diagnosticsRecordingHash(agentId, episode.capture.recording_id)}>Open saved collection</a>}
        <dl className="episode-context">{Object.entries(episode.capture.coverage).map(([label, value]) => <div key={label}><dt>{label.replaceAll("_", " ")}</dt><dd>{String(value ?? "—")}</dd></div>)}</dl></> : <p>Automatic capture was disabled when this episode was confirmed.</p>}
      <h2>Episode timeline</h2><ol className="episode-timeline">{episode.transitions.map((transition, index) => <li key={`${transition.kind}-${transition.observed_at}-${index}`}><strong>{transition.kind.replaceAll("_", " ")}</strong><time>{date(transition.observed_at)}</time>{typeof transition.data.reason === "string" && <p>{transition.data.reason}</p>}</li>)}</ol>{episode.transitions_truncated && <p>Showing the latest 200 transitions.</p>}
    </>}
  </section>;
}
