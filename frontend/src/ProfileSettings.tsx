import { useEffect, useState } from "react";

import {
  activateProfile,
  createProfile,
  getProfile,
  getProfiles,
  getProfileVersions,
  updateProfile,
} from "./api";
import { validateProfileConfiguration } from "./profileValidation";
import type {
  TestProfileConfiguration,
  TestProfileSummary,
  TestProfileVersion,
  TestProfileWrite,
} from "./types";


const defaultConfiguration: TestProfileConfiguration = {
  schema_version: 1,
  sampling: { wifi_interval_seconds: 5 },
  tests: {
    gateway: {
      enabled: true,
      interval_seconds: 5,
      timeout_seconds: 6,
      automatic_gateway: true,
      target: null,
    },
    dns: {
      enabled: true,
      interval_seconds: 5,
      timeout_seconds: null,
      query: "example.com",
    },
    internet: {
      enabled: true,
      interval_seconds: 5,
      timeout_seconds: 6,
      target: "1.1.1.1",
    },
    https: {
      enabled: true,
      interval_seconds: 5,
      timeout_seconds: 5,
      url: "https://example.com",
    },
  },
  thresholds: {
    wifi: {
      rssi_warning_dbm: -75,
      rssi_critical_dbm: -82,
      retry_warning_percent: 20,
      retry_critical_percent: 50,
      tx_failure_critical_percent: 5,
    },
    gateway: {
      latency_warning_ms: 50,
      packet_loss_warning_percent: 5,
      packet_loss_critical_percent: 20,
    },
    dns: { latency_warning_ms: 250 },
    internet: {
      latency_warning_ms: 150,
      packet_loss_warning_percent: 5,
      packet_loss_critical_percent: 20,
    },
    https: { response_warning_ms: 1000 },
    connection_cycle: {
      window_size: 20,
      minimum_samples: 5,
      p95_warning_ms: 8000,
      p95_critical_ms: 15000,
    },
    adaptive_baseline: {
      enabled: true,
      lookback_hours: 24,
      minimum_samples: 30,
      max_samples: 1000,
      warning_sigma: 3.5,
      critical_sigma: 6,
    },
    service_slo: {
      enabled: true,
      window_size: 60,
      minimum_samples: 20,
      gateway: {
        availability_warning_percent: 99,
        availability_critical_percent: 95,
        latency_p95_warning_ms: 50,
        latency_p95_critical_ms: 100,
        packet_loss_p95_warning_percent: 5,
        packet_loss_p95_critical_percent: 20,
      },
      internet: {
        availability_warning_percent: 99,
        availability_critical_percent: 95,
        latency_p95_warning_ms: 150,
        latency_p95_critical_ms: 300,
        packet_loss_p95_warning_percent: 5,
        packet_loss_p95_critical_percent: 20,
      },
      dns: {
        availability_warning_percent: 99,
        availability_critical_percent: 95,
        latency_p95_warning_ms: 250,
        latency_p95_critical_ms: 500,
        packet_loss_p95_warning_percent: null,
        packet_loss_p95_critical_percent: null,
      },
      https: {
        availability_warning_percent: 99,
        availability_critical_percent: 95,
        latency_p95_warning_ms: 1000,
        latency_p95_critical_ms: 2000,
        packet_loss_p95_warning_percent: null,
        packet_loss_p95_critical_percent: null,
      },
    },
  },
};


function cloneConfiguration(
  configuration: TestProfileConfiguration,
): TestProfileConfiguration {
  return JSON.parse(JSON.stringify(configuration)) as TestProfileConfiguration;
}


function newProfile(): TestProfileWrite {
  return {
    name: "New profile",
    description: null,
    enabled: true,
    configuration: cloneConfiguration(defaultConfiguration),
  };
}


function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = "any",
  nullable = false,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  min?: number;
  max?: number;
  step?: number | "any";
  nullable?: boolean;
}) {
  return (
    <label>
      <span>{label}</span>
      <input
        type="number"
        value={value ?? ""}
        min={min}
        max={max}
        step={step}
        onChange={(event) => {
          onChange(event.target.value === "" && nullable
            ? null : Number(event.target.value));
        }}
      />
    </label>
  );
}


function ProfileSettings({ sensorRunning }: { sensorRunning: boolean }) {
  const [profiles, setProfiles] = useState<TestProfileSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [draft, setDraft] = useState<TestProfileWrite | null>(null);
  const [versions, setVersions] = useState<TestProfileVersion[]>([]);
  const [inspectedVersion, setInspectedVersion] = useState<TestProfileVersion | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selected = profiles.find((profile) => profile.id === selectedId) ?? null;

  async function selectProfile(profileId: number) {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const [profile, profileVersions] = await Promise.all([
        getProfile(profileId),
        getProfileVersions(profileId),
      ]);
      setSelectedId(profileId);
      setDraft({
        name: profile.name,
        description: profile.description,
        enabled: profile.enabled,
        configuration: cloneConfiguration(profile.configuration),
      });
      setVersions(profileVersions);
      setInspectedVersion(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load profile.");
    } finally {
      setLoading(false);
    }
  }

  async function refreshProfiles(preferredId?: number) {
    setLoading(true);
    setError(null);
    try {
      const items = await getProfiles();
      setProfiles(items);
      const target = preferredId
        ?? items.find((profile) => profile.active)?.id
        ?? items[0]?.id;
      if (target !== undefined) {
        await selectProfile(target);
      } else {
        setSelectedId(null);
        setDraft(newProfile());
        setVersions([]);
        setLoading(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load profiles.");
      setLoading(false);
    }
  }

  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect
    void refreshProfiles();
  }, []);

  function updateConfiguration(
    mutator: (configuration: TestProfileConfiguration) => void,
  ) {
    if (draft === null) return;
    const configuration = cloneConfiguration(draft.configuration);
    mutator(configuration);
    setDraft({ ...draft, configuration });
  }

  function updateTestField(
    testName: keyof TestProfileConfiguration["tests"],
    field: string,
    value: unknown,
  ) {
    updateConfiguration((configuration) => {
      const test = configuration.tests[testName] as unknown as Record<string, unknown>;
      test[field] = value;
    });
  }

  function beginCreate() {
    setSelectedId(null);
    setDraft(newProfile());
    setVersions([]);
    setInspectedVersion(null);
    setError(null);
    setNotice(null);
  }

  async function saveProfile() {
    if (draft === null) return;
    const validationErrors = validateProfileConfiguration(draft.configuration);
    if (!draft.name.trim()) validationErrors.unshift("Profile name is required.");
    if (validationErrors.length > 0) {
      setError(validationErrors.join(" "));
      return;
    }

    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const payload = { ...draft, name: draft.name.trim() };
      const saved = selectedId === null
        ? await createProfile(payload)
        : await updateProfile(selectedId, payload);
      await refreshProfiles(saved.id);
      setNotice(`Profile saved as version ${saved.version}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save profile.");
    } finally {
      setSaving(false);
    }
  }

  async function makeActive() {
    if (selectedId === null) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const activated = await activateProfile(selectedId);
      await refreshProfiles(activated.id);
      setNotice(sensorRunning
        ? "Profile activated. The running session keeps its pinned version until monitoring restarts."
        : "Profile activated. It will be used when monitoring starts.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to activate profile.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="profile-settings">
      <aside className="profile-list panel">
        <div className="profile-heading">
          <div>
            <h2>Test profiles</h2>
            <p className="metric-note">Choose the active measurements and diagnostic limits.</p>
          </div>
          <button type="button" onClick={beginCreate}>New profile</button>
        </div>
        <div className="profile-list-items">
          {profiles.map((profile) => (
            <button
              type="button"
              key={profile.id}
              disabled={saving}
              className={profile.id === selectedId ? "profile-list-item profile-selected" : "profile-list-item"}
              onClick={() => void selectProfile(profile.id)}
            >
              <span>
                <strong>{profile.name}</strong>
                <small>Version {profile.version}{!profile.enabled ? " · disabled" : ""}</small>
              </span>
              {profile.active && <em>ACTIVE</em>}
            </button>
          ))}
        </div>
      </aside>

      <div className="profile-editor">
        {error && <div className="error" role="alert">{error}</div>}
        {notice && <div className="profile-notice" role="status">{notice}</div>}
        {sensorRunning && (
          <div className="profile-session-note">
            Monitoring is running with its previously pinned profile version. Saved or activated
            changes take effect after Stop and Start.
          </div>
        )}
        {loading && draft === null ? <div className="empty-state">Loading profiles…</div> : null}
        {draft && (
          <form onSubmit={(event) => { event.preventDefault(); void saveProfile(); }}>
            <section className="panel profile-section">
              <div className="profile-heading">
                <div>
                  <h2>{selectedId === null ? "Create profile" : `Edit ${selected?.name ?? "profile"}`}</h2>
                  {selected && <p className="metric-note">Current version {selected.version} · Updated {new Date(selected.updated_at).toLocaleString()}</p>}
                </div>
                <div className="profile-actions">
                  {selectedId !== null && (
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={saving || selected?.active || !draft.enabled}
                      onClick={() => void makeActive()}
                    >
                      {selected?.active ? "Active profile" : "Activate"}
                    </button>
                  )}
                  <button type="submit" disabled={saving}>
                    {saving ? "Saving…" : selectedId === null ? "Create profile" : "Save new version"}
                  </button>
                </div>
              </div>
              <div className="profile-form-grid">
                <label>
                  <span>Name</span>
                  <input value={draft.name} maxLength={100} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
                </label>
                <label className="profile-wide-field">
                  <span>Description</span>
                  <input value={draft.description ?? ""} maxLength={2000} onChange={(event) => setDraft({ ...draft, description: event.target.value || null })} />
                </label>
                <label className="profile-toggle">
                  <input
                    type="checkbox"
                    checked={draft.enabled}
                    disabled={selected?.active}
                    onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })}
                  />
                  <span>Enabled{selected?.active ? " · active profiles cannot be disabled" : ""}</span>
                </label>
                <NumberField
                  label="Wi-Fi sampling interval (seconds)"
                  value={draft.configuration.sampling.wifi_interval_seconds}
                  min={1}
                  max={3600}
                  onChange={(value) => updateConfiguration((configuration) => {
                    configuration.sampling.wifi_interval_seconds = value ?? 0;
                  })}
                />
              </div>
            </section>

            <section className="panel profile-section">
              <h2>Synthetic tests</h2>
              <p className="metric-note">Enabled intervals must be integer multiples of the Wi-Fi sampling interval.</p>
              <div className="test-profile-grid">
                {(Object.keys(draft.configuration.tests) as Array<keyof TestProfileConfiguration["tests"]>).map((name) => {
                  const test = draft.configuration.tests[name];
                  return (
                    <fieldset key={name} className="test-profile-card">
                      <legend>{name.toUpperCase()}</legend>
                      <label className="profile-toggle">
                        <input type="checkbox" checked={test.enabled} onChange={(event) => updateTestField(name, "enabled", event.target.checked)} />
                        <span>Enabled</span>
                      </label>
                      <NumberField label="Interval (seconds)" value={test.interval_seconds} min={1} max={86400} onChange={(value) => updateTestField(name, "interval_seconds", value ?? 0)} />
                      <NumberField label="Timeout (seconds)" value={test.timeout_seconds} min={0.1} max={300} nullable onChange={(value) => updateTestField(name, "timeout_seconds", value)} />
                      {name === "gateway" && <>
                        <label className="profile-toggle">
                          <input type="checkbox" checked={draft.configuration.tests.gateway.automatic_gateway} onChange={(event) => updateTestField("gateway", "automatic_gateway", event.target.checked)} />
                          <span>Detect gateway automatically</span>
                        </label>
                        <label><span>Explicit target</span><input disabled={draft.configuration.tests.gateway.automatic_gateway} value={draft.configuration.tests.gateway.target ?? ""} onChange={(event) => updateTestField("gateway", "target", event.target.value || null)} /></label>
                      </>}
                      {name === "dns" && <label><span>DNS query</span><input value={draft.configuration.tests.dns.query} onChange={(event) => updateTestField("dns", "query", event.target.value)} /></label>}
                      {name === "internet" && <label><span>ICMP target</span><input value={draft.configuration.tests.internet.target} onChange={(event) => updateTestField("internet", "target", event.target.value)} /></label>}
                      {name === "https" && <label><span>HTTP/HTTPS URL</span><input type="url" value={draft.configuration.tests.https.url} onChange={(event) => updateTestField("https", "url", event.target.value)} /></label>}
                    </fieldset>
                  );
                })}
              </div>
            </section>

            <section className="panel profile-section">
              <h2>Diagnostic thresholds</h2>
              <div className="threshold-grid">
                <fieldset>
                  <legend>Wi-Fi</legend>
                  {([
                    ["rssi_warning_dbm", "RSSI warning (dBm)"],
                    ["rssi_critical_dbm", "RSSI critical (dBm)"],
                    ["retry_warning_percent", "Retries warning (%)"],
                    ["retry_critical_percent", "Retries critical (%)"],
                    ["tx_failure_critical_percent", "TX failures critical (%)"],
                  ] as const).map(([key, label]) => (
                    <NumberField key={key} label={label} value={draft.configuration.thresholds.wifi[key]} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.wifi[key] = value ?? 0; })} />
                  ))}
                </fieldset>
                {(["gateway", "internet"] as const).map((name) => (
                  <fieldset key={name}>
                    <legend>{name[0].toUpperCase() + name.slice(1)}</legend>
                    <NumberField label="Latency warning (ms)" min={0.1} value={draft.configuration.thresholds[name].latency_warning_ms} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds[name].latency_warning_ms = value ?? 0; })} />
                    <NumberField label="Packet loss warning (%)" min={0} max={100} value={draft.configuration.thresholds[name].packet_loss_warning_percent} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds[name].packet_loss_warning_percent = value ?? 0; })} />
                    <NumberField label="Packet loss critical (%)" min={0} max={100} value={draft.configuration.thresholds[name].packet_loss_critical_percent} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds[name].packet_loss_critical_percent = value ?? 0; })} />
                  </fieldset>
                ))}
                <fieldset>
                  <legend>DNS</legend>
                  <NumberField label="Latency warning (ms)" min={0.1} value={draft.configuration.thresholds.dns.latency_warning_ms} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.dns.latency_warning_ms = value ?? 0; })} />
                </fieldset>
                <fieldset>
                  <legend>HTTPS</legend>
                  <NumberField label="Response warning (ms)" min={0.1} value={draft.configuration.thresholds.https.response_warning_ms} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.https.response_warning_ms = value ?? 0; })} />
                </fieldset>
                <fieldset>
                  <legend>Connection cycle SLO</legend>
                  <NumberField label="Rolling window (cycles)" min={3} max={200} step={1} value={draft.configuration.thresholds.connection_cycle.window_size} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.connection_cycle.window_size = value ?? 0; })} />
                  <NumberField label="Minimum samples" min={3} max={200} step={1} value={draft.configuration.thresholds.connection_cycle.minimum_samples} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.connection_cycle.minimum_samples = value ?? 0; })} />
                  <NumberField label="P95 warning (ms)" min={0.1} value={draft.configuration.thresholds.connection_cycle.p95_warning_ms} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.connection_cycle.p95_warning_ms = value ?? 0; })} />
                  <NumberField label="P95 critical (ms)" min={0.1} value={draft.configuration.thresholds.connection_cycle.p95_critical_ms} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.connection_cycle.p95_critical_ms = value ?? 0; })} />
                  <p className="metric-note">Only unique connection cycles with a measured network-ready duration enter the rolling P95.</p>
                </fieldset>
                <fieldset>
                  <legend>Synthetic service SLO</legend>
                  <label className="profile-toggle">
                    <input type="checkbox" checked={draft.configuration.thresholds.service_slo.enabled} onChange={(event) => updateConfiguration((configuration) => { configuration.thresholds.service_slo.enabled = event.target.checked; })} />
                    <span>Evaluate rolling availability and tail performance</span>
                  </label>
                  <NumberField label="Rolling window (executions)" min={10} max={1000} step={1} value={draft.configuration.thresholds.service_slo.window_size} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.service_slo.window_size = value ?? 0; })} />
                  <NumberField label="Minimum definitive samples" min={5} max={1000} step={1} value={draft.configuration.thresholds.service_slo.minimum_samples} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.service_slo.minimum_samples = value ?? 0; })} />
                  {(["gateway", "internet", "dns", "https"] as const).map((name) => {
                    const target = draft.configuration.thresholds.service_slo[name];
                    const packetLoss = name === "gateway" || name === "internet";
                    return <details key={name}>
                      <summary>{name.toUpperCase()} policy</summary>
                      <NumberField label="Availability warning below (%)" min={0} max={100} value={target.availability_warning_percent} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.service_slo[name].availability_warning_percent = value ?? 0; })} />
                      <NumberField label="Availability critical below (%)" min={0} max={100} value={target.availability_critical_percent} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.service_slo[name].availability_critical_percent = value ?? 0; })} />
                      <NumberField label="Latency P95 warning (ms)" min={0.1} value={target.latency_p95_warning_ms} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.service_slo[name].latency_p95_warning_ms = value ?? 0; })} />
                      <NumberField label="Latency P95 critical (ms)" min={0.1} value={target.latency_p95_critical_ms} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.service_slo[name].latency_p95_critical_ms = value ?? 0; })} />
                      {packetLoss && <>
                        <NumberField label="Packet-loss P95 warning (%)" min={0} max={100} value={target.packet_loss_p95_warning_percent} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.service_slo[name].packet_loss_p95_warning_percent = value; })} />
                        <NumberField label="Packet-loss P95 critical (%)" min={0} max={100} value={target.packet_loss_p95_critical_percent} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.service_slo[name].packet_loss_p95_critical_percent = value; })} />
                      </>}
                    </details>;
                  })}
                  <p className="metric-note">
                    Availability counts only definitive passed/failed executions. Sensor collection
                    errors are tracked separately and cached test results are never counted twice.
                  </p>
                </fieldset>
                <fieldset>
                  <legend>Adaptive baseline</legend>
                  <label className="profile-toggle">
                    <input type="checkbox" checked={draft.configuration.thresholds.adaptive_baseline.enabled} onChange={(event) => updateConfiguration((configuration) => { configuration.thresholds.adaptive_baseline.enabled = event.target.checked; })} />
                    <span>Evaluate same-SSID historical deviations</span>
                  </label>
                  <NumberField label="Lookback (hours)" min={1} max={168} step={1} value={draft.configuration.thresholds.adaptive_baseline.lookback_hours} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.adaptive_baseline.lookback_hours = value ?? 0; })} />
                  <NumberField label="Minimum samples" min={10} max={5000} step={1} value={draft.configuration.thresholds.adaptive_baseline.minimum_samples} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.adaptive_baseline.minimum_samples = value ?? 0; })} />
                  <NumberField label="Maximum samples" min={30} max={10000} step={1} value={draft.configuration.thresholds.adaptive_baseline.max_samples} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.adaptive_baseline.max_samples = value ?? 0; })} />
                  <NumberField label="Warning deviation (robust σ)" min={0.1} max={20} value={draft.configuration.thresholds.adaptive_baseline.warning_sigma} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.adaptive_baseline.warning_sigma = value ?? 0; })} />
                  <NumberField label="Critical deviation (robust σ)" min={0.1} max={30} value={draft.configuration.thresholds.adaptive_baseline.critical_sigma} onChange={(value) => updateConfiguration((configuration) => { configuration.thresholds.adaptive_baseline.critical_sigma = value ?? 0; })} />
                  <p className="metric-note">
                    Uses the median and median absolute deviation from prior measurements on the
                    same interface and SSID. Cached synthetic-test results are not learned twice.
                  </p>
                </fieldset>
              </div>
            </section>

            {selectedId !== null && (
              <section className="panel profile-section">
                <h2>Version history</h2>
                <div className="table-wrapper">
                  <table>
                    <thead><tr><th>Version</th><th>Created</th><th>Status</th><th>Configuration</th></tr></thead>
                    <tbody>{versions.map((version) => (
                      <tr key={version.id}>
                        <td>v{version.version}</td>
                        <td>{new Date(version.created_at).toLocaleString()}</td>
                        <td>{version.active ? "Active" : "Immutable"}</td>
                        <td><button type="button" className="link-button" onClick={() => setInspectedVersion(version)}>Inspect</button></td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
                {inspectedVersion && (
                  <details open className="profile-version-json">
                    <summary>Version {inspectedVersion.version} configuration</summary>
                    <pre>{JSON.stringify(inspectedVersion.configuration, null, 2)}</pre>
                  </details>
                )}
              </section>
            )}
          </form>
        )}
      </div>
    </div>
  );
}


export default ProfileSettings;
