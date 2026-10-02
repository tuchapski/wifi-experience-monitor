import { useEffect, useState, type FormEvent } from "react";
import { getExperienceProfile, saveExperienceProfile } from "./agentApi";
import type { ExperienceProfile, ExperienceProfileResponse, ServiceObjectives } from "./agentTypes";

const SERVICES = [["local_network", "Local network"], ["dns", "DNS"], ["internet", "Internet"], ["application", "Application"]] as const;

export default function ExperienceProfileEditor({ agentId }: { agentId: string }) {
  const [saved, setSaved] = useState<ExperienceProfileResponse | null>(null);
  const [draft, setDraft] = useState<ExperienceProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    void getExperienceProfile(agentId).then(data => {
      if (active) { setSaved(data); setDraft(data.profile); }
    }).catch(err => { if (active) setError(err instanceof Error ? err.message : "Unable to load profile"); });
    return () => { active = false; };
  }, [agentId]);

  async function reload() {
    setBusy(true);
    try { const data = await getExperienceProfile(agentId); setSaved(data); setDraft(data.profile); setError(null); setMessage("Latest profile loaded."); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to load profile"); }
    finally { setBusy(false); }
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft || !saved || busy) return;
    setBusy(true); setMessage(null); setError(null);
    try {
      const result = await saveExperienceProfile(agentId, saved.version, draft);
      setSaved(result); setDraft(result.profile);
      setMessage("Profile saved. The Agent will apply it at the next safe probe boundary.");
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to save profile"); }
    finally { setBusy(false); }
  }
  function text(key: "name" | "location" | "dns_query" | "internet_target" | "https_url", value: string) {
    setDraft(current => current ? { ...current, [key]: value } : current);
  }
  function number(key: "interval_seconds" | "timeout_seconds" | "confirm_seconds" | "recover_seconds" | "capture_pre_seconds" | "capture_post_seconds" | "capture_cooldown_seconds", value: string) {
    setDraft(current => current ? { ...current, [key]: Number(value) } : current);
  }
  function objective(service: typeof SERVICES[number][0], key: keyof ServiceObjectives, value: string) {
    setDraft(current => current ? { ...current, [service]: { ...current[service], [key]: value === "" ? null : Number(value) } } : current);
  }
  return <details className="experience-profile-editor"><summary>Targets and performance objectives</summary>
    <p>Use stable targets relevant to this client. Saving a changed profile rebuilds its references. Blank time objectives keep relative comparison; blank packet loss objectives disable that rule.</p>
    {error && <p role="alert" className="agent-error">{error}</p>}
    {!draft ? <button type="button" onClick={() => void reload()} disabled={busy}>Reload profile</button> : <form onSubmit={event => void save(event)}>
      <fieldset disabled={busy}>
        <label className="detector-enabled"><input type="checkbox" checked={draft.enabled} onChange={event => setDraft({ ...draft, enabled: event.target.checked })} />Enable continuous detection for this client</label>
        <div className="detector-profile-grid">
          <label>Profile name<input required maxLength={128} value={draft.name} onChange={event => text("name", event.target.value)} /></label>
          <label>Measurement location<input maxLength={128} value={draft.location} onChange={event => text("location", event.target.value)} placeholder="Office desk / meeting room" /></label>
          <label>DNS query<input required maxLength={253} value={draft.dns_query} onChange={event => text("dns_query", event.target.value)} /></label>
          <label>Internet ICMP target<input required maxLength={253} value={draft.internet_target} onChange={event => text("internet_target", event.target.value)} /></label>
          <label className="detector-profile-url">Application HTTPS URL<input required type="url" maxLength={2048} value={draft.https_url} onChange={event => text("https_url", event.target.value)} /></label>
          <label>Probe interval (s)<input required type="number" min={5} max={20} step="any" value={draft.interval_seconds} onChange={event => number("interval_seconds", event.target.value)} /></label>
          <label>Probe timeout (s)<input required type="number" min={1} max={10} step="any" value={draft.timeout_seconds} onChange={event => number("timeout_seconds", event.target.value)} /></label>
          <label>Confirm degradation after (s)<input required type="number" min={5} max={300} step="any" value={draft.confirm_seconds} onChange={event => number("confirm_seconds", event.target.value)} /></label>
          <label>Confirm recovery after (s)<input required type="number" min={5} max={300} step="any" value={draft.recover_seconds} onChange={event => number("recover_seconds", event.target.value)} /></label>
        </div>
        <label className="detector-enabled"><input type="checkbox" checked={draft.automatic_capture ?? false} onChange={event => setDraft({ ...draft, automatic_capture: event.target.checked })} />Automatically capture individual episodes</label>
        <p>One capture per episode. Existing individual collections are reused without extending their deadline. The window ends after the trigger, even if the episode remains active. Before enabling, allow the Agent to build its local buffer.</p>
        {draft.automatic_capture && <div className="detector-profile-grid">
          <label>Before episode onset (s)<input required type="number" min={0} max={300} value={draft.capture_pre_seconds} onChange={event => number("capture_pre_seconds", event.target.value)} /></label>
          <label>After confirmation trigger (s)<input required type="number" min={30} max={900} value={draft.capture_post_seconds} onChange={event => number("capture_post_seconds", event.target.value)} /></label>
          <label>Minimum time between new captures (s)<input required type="number" min={30} max={3600} value={draft.capture_cooldown_seconds} onChange={event => number("capture_cooldown_seconds", event.target.value)} /></label>
        </div>}
        <div className="detector-objectives">{SERVICES.map(([key, label]) => <div key={key}><h3>{label}</h3>
          <label>{key === "application" ? "Total HTTP time" : "Latency"} objective (ms)<input type="number" min={0.001} max={60000} step="any" value={draft[key].latency_ms ?? ""} onChange={event => objective(key, "latency_ms", event.target.value)} /></label>
          {["local_network", "internet"].includes(key) && <>
            <label>Packet loss objective (%)<input type="number" min={0} max={100} step="any" value={draft[key].packet_loss_percent ?? ""} onChange={event => objective(key, "packet_loss_percent", event.target.value)} /></label>
            <label>Jitter objective (ms)<input type="number" min={0.001} max={60000} step="any" value={draft[key].jitter_ms ?? ""} onChange={event => objective(key, "jitter_ms", event.target.value)} /></label>
          </>}
          {key === "application" && <label>TTFB objective (ms)<input type="number" min={0.001} max={60000} step="any" value={draft[key].ttfb_ms ?? ""} onChange={event => objective(key, "ttfb_ms", event.target.value)} /></label>}
        </div>)}</div>
        <p>Gateway tests follow the current default gateway. Degradation requires at least {draft.minimum_samples} distinct samples; recovery requires at least two. References need {draft.baseline_min_samples} successful samples spanning at least {draft.baseline_min_seconds}s and then freeze. Targets can be served from caches, and ICMP loss is based on four packets per probe.</p>
        <div className="detector-profile-actions"><button type="submit">{busy ? "Saving…" : "Save profile"}</button><button type="button" onClick={() => void reload()}>Reload saved profile</button></div>
      </fieldset>
    </form>}
    {message && <p role="status">{message}</p>}
  </details>;
}
