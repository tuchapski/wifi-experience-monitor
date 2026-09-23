import { useEffect, useState } from "react";

import {
  getProfile,
  getProfiles,
  updateProfile,
} from "./api";
import ApplicationTargetsPanel from "./ApplicationTargetsPanel";
import { validateProfileConfiguration } from "./profileValidation";
import type {
  ApplicationTargetConfiguration,
  ApplicationTargetMetric,
  TestProfile,
  TestProfileConfiguration,
  TestProfileSummary,
} from "./types";


function cloneConfiguration(
  configuration: TestProfileConfiguration,
): TestProfileConfiguration {
  return JSON.parse(JSON.stringify(configuration)) as TestProfileConfiguration;
}


function cloneTargets(
  targets: ApplicationTargetConfiguration[],
): ApplicationTargetConfiguration[] {
  return JSON.parse(JSON.stringify(targets)) as ApplicationTargetConfiguration[];
}


function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  nullable = false,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  min?: number;
  max?: number;
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
        step="any"
        onChange={(event) => {
          onChange(event.target.value === "" && nullable
            ? null
            : Number(event.target.value));
        }}
      />
    </label>
  );
}


export default function ApplicationsPanel({
  targets,
  sensorRunning,
  active,
}: {
  targets?: Record<string, ApplicationTargetMetric>;
  sensorRunning: boolean;
  active: boolean;
}) {
  const [profiles, setProfiles] = useState<TestProfileSummary[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null);
  const [profile, setProfile] = useState<TestProfile | null>(null);
  const [draftTargets, setDraftTargets] = useState<ApplicationTargetConfiguration[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  const observedTargets = Object.values(targets ?? {});
  const passed = observedTargets.filter((target) => target.status === "passed").length;
  const failed = observedTargets.filter((target) => target.status === "failed").length;
  const unavailable = observedTargets.length - passed - failed;

  async function loadProfile(profileId: number) {
    const loaded = await getProfile(profileId);
    setSelectedProfileId(profileId);
    setProfile(loaded);
    setDraftTargets(cloneTargets(loaded.configuration.application_targets));
    setDirty(false);
  }

  async function refreshProfiles(preferredId?: number | null) {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const items = await getProfiles();
      setProfiles(items);
      const targetId = preferredId !== null && preferredId !== undefined
        && items.some((item) => item.id === preferredId)
        ? preferredId
        : items.find((item) => item.active)?.id ?? items[0]?.id;
      if (targetId === undefined) {
        setSelectedProfileId(null);
        setProfile(null);
        setDraftTargets([]);
        setError("No monitoring profile is available.");
        return;
      }
      await loadProfile(targetId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load application targets.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!active || dirty) return;
    void refreshProfiles(selectedProfileId);
  }, [active]);

  async function selectProfile(profileId: number) {
    if (dirty && !window.confirm("Discard unsaved target changes and load another profile?")) {
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      await loadProfile(profileId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load application targets.");
    } finally {
      setLoading(false);
    }
  }

  function addTarget() {
    if (draftTargets.length >= 20) return;
    let suffix = draftTargets.length + 1;
    const used = new Set(draftTargets.map((item) => item.name.toLowerCase()));
    while (used.has(`application ${suffix}`)) suffix += 1;
    setDraftTargets([
      ...draftTargets,
      {
        name: `Application ${suffix}`,
        kind: "http",
        target: "https://example.com",
        port: null,
        enabled: true,
        interval_seconds: 60,
        timeout_seconds: 5,
      },
    ]);
    setNotice(null);
    setDirty(true);
  }

  function updateTarget(
    index: number,
    field: keyof ApplicationTargetConfiguration,
    value: string | number | boolean | null,
  ) {
    setDraftTargets((current) => current.map((target, targetIndex) => {
      if (targetIndex !== index) return target;
      const updated = { ...target, [field]: value } as ApplicationTargetConfiguration;
      if (field === "kind" && value !== "tcp") updated.port = null;
      if (field === "kind" && value === "tcp" && updated.port === null) updated.port = 443;
      return updated;
    }));
    setNotice(null);
    setDirty(true);
  }

  function removeTarget(index: number) {
    setDraftTargets((current) => current.filter((_, targetIndex) => targetIndex !== index));
    setNotice(null);
    setDirty(true);
  }

  async function saveTargets() {
    if (selectedProfileId === null) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const latest = await getProfile(selectedProfileId);
      const configuration = cloneConfiguration(latest.configuration);
      configuration.application_targets = cloneTargets(draftTargets);
      const validationErrors = validateProfileConfiguration(configuration);
      if (validationErrors.length > 0) {
        setError(validationErrors.join(" "));
        return;
      }

      const saved = await updateProfile(latest.id, {
        name: latest.name,
        description: latest.description,
        enabled: latest.enabled,
        configuration,
      });
      setProfile(saved);
      setDraftTargets(cloneTargets(saved.configuration.application_targets));
      setDirty(false);
      setProfiles((current) => current.map((item) => item.id === saved.id ? saved : item));
      setNotice(
        sensorRunning && saved.active
          ? `Targets saved in ${saved.name} v${saved.version}. Restart monitoring to apply them to the running sensor.`
          : saved.active
            ? `Targets saved in active profile ${saved.name} v${saved.version}.`
            : `Targets saved in ${saved.name} v${saved.version}. Activate this profile to use them.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save application targets.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <section className="panel applications-overview" aria-labelledby="applications-title">
        <div>
          <h2 id="applications-title">Application experience</h2>
          <p className="metric-note">
            Current target health and user-defined application dependencies. Target probes use the
            host route and are not proof that traffic was bound to the selected Wi-Fi interface.
          </p>
        </div>
        <div className="application-summary-grid" aria-label="Application target summary">
          <div><span>Observed</span><strong>{observedTargets.length}</strong></div>
          <div><span>Healthy</span><strong className="status-healthy">{passed}</strong></div>
          <div><span>Failed</span><strong className={failed > 0 ? "status-critical" : ""}>{failed}</strong></div>
          <div><span>Other / unavailable</span><strong>{unavailable}</strong></div>
        </div>
      </section>

      {observedTargets.length > 0
        ? <ApplicationTargetsPanel targets={targets} />
        : <section className="panel">
          <h2>Current application health</h2>
          <div className="empty-state">
            No application-target result is available in the current monitoring session.
          </div>
        </section>}

      <section className="panel profile-section application-target-settings"
        aria-labelledby="application-target-settings-title">
        <div className="profile-heading">
          <div>
            <h2 id="application-target-settings-title">Monitored targets</h2>
            <p className="metric-note">
              Targets remain part of the immutable versioned profile, but are managed here because
              they describe what applications the sensor monitors.
            </p>
          </div>
          <button type="button" onClick={addTarget}
            disabled={loading || saving || profile === null || draftTargets.length >= 20}>
            Add target
          </button>
        </div>

        <div className="application-profile-row">
          <label>
            <span>Target configuration profile</span>
            <select
              value={selectedProfileId ?? ""}
              disabled={loading || saving || profiles.length === 0}
              onChange={(event) => void selectProfile(Number(event.target.value))}
            >
              {profiles.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · v{item.version}{item.active ? " · ACTIVE" : ""}
                </option>
              ))}
            </select>
          </label>
          {profile && <p className="metric-note">
            Editing {profile.name} v{profile.version}. Saving creates a new immutable version of
            this profile without changing its other monitoring settings.
          </p>}
        </div>

        {sensorRunning && profile?.active && <div className="profile-session-note">
          The running monitoring session keeps its pinned profile version. Saved target changes
          take effect after Stop and Start.
        </div>}
        {error && <div className="error" role="alert">{error}</div>}
        {notice && <div className="profile-notice" role="status">{notice}</div>}
        {loading ? <div className="empty-state">Loading application targets…</div>
          : draftTargets.length === 0 ? (
            <div className="empty-state">No application targets configured for this profile.</div>
          ) : (
            <div className="test-profile-grid">
              {draftTargets.map((target, index) => (
                <fieldset key={`${index}-${target.name}`} className="test-profile-card">
                  <legend>{target.name || `Target ${index + 1}`}</legend>
                  <label className="profile-toggle">
                    <input type="checkbox" checked={target.enabled}
                      onChange={(event) => updateTarget(index, "enabled", event.target.checked)} />
                    <span>Enabled</span>
                  </label>
                  <label><span>Name</span><input value={target.name} maxLength={80}
                    onChange={(event) => updateTarget(index, "name", event.target.value)} /></label>
                  <label><span>Type</span><select value={target.kind}
                    onChange={(event) => updateTarget(index, "kind", event.target.value)}>
                    <option value="http">HTTP / HTTPS</option>
                    <option value="tcp">TCP</option>
                    <option value="dns">DNS</option>
                  </select></label>
                  <label><span>{target.kind === "http" ? "URL"
                    : target.kind === "tcp" ? "Host / IP" : "DNS query"}</span>
                    <input value={target.target}
                      onChange={(event) => updateTarget(index, "target", event.target.value)} /></label>
                  {target.kind === "tcp" && <NumberField label="TCP port" value={target.port}
                    min={1} max={65535} onChange={(value) => updateTarget(index, "port", value)} />}
                  <NumberField label="Interval (seconds)" value={target.interval_seconds}
                    min={1} max={86400}
                    onChange={(value) => updateTarget(index, "interval_seconds", value ?? 0)} />
                  <NumberField label="Timeout (seconds)" value={target.timeout_seconds}
                    min={0.1} max={300} nullable
                    onChange={(value) => updateTarget(index, "timeout_seconds", value)} />
                  <button type="button" className="link-button"
                    onClick={() => removeTarget(index)}>Remove target</button>
                </fieldset>
              ))}
            </div>
          )}

        <div className="application-target-actions">
          <button type="button" onClick={() => void refreshProfiles(selectedProfileId)}
            className="secondary-button" disabled={loading || saving || profile === null || !dirty}>
            Discard changes
          </button>
          <button type="button" onClick={() => void saveTargets()}
            disabled={loading || saving || profile === null || !dirty}>
            {saving ? "Saving…" : "Save targets"}
          </button>
        </div>
      </section>
    </>
  );
}
