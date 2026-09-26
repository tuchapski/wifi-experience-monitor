import { type FormEvent, useState } from "react";

import type { StartRecordingInput } from "./agentTypes";
import "./CollectionStartForm.css";

const DURATIONS = [15, 30, 60, 120, 240, 480, 1440];

export default function CollectionStartForm({
  disabled = false,
  busy = false,
  onSubmit,
}: {
  disabled?: boolean;
  busy?: boolean;
  onSubmit: (input: StartRecordingInput) => Promise<boolean>;
}) {
  const [name, setName] = useState("");
  const [site, setSite] = useState("");
  const [location, setLocation] = useState("");
  const [notes, setNotes] = useState("");
  const [duration, setDuration] = useState(60);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (disabled || busy) return;

    const started = await onSubmit({
      name: name.trim() || `Diagnostic ${new Date().toLocaleString()}`,
      description: notes.trim() || null,
      site: site.trim() || null,
      location: location.trim() || null,
      profile_id: "wifi-deep-dive",
      max_duration_minutes: duration,
    });

    if (!started) return;
    setName("");
    setSite("");
    setLocation("");
    setNotes("");
  }

  return (
    <form className="collection-start-form" onSubmit={(event) => void handleSubmit(event)}>
      <div className="collection-start-grid">
        <label>
          Collection name
          <input
            maxLength={255}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Optional collection name"
            disabled={disabled || busy}
          />
        </label>
        <label>
          Maximum duration
          <select
            value={duration}
            onChange={(event) => setDuration(Number(event.target.value))}
            disabled={disabled || busy}
          >
            {DURATIONS.map((minutes) => (
              <option key={minutes} value={minutes}>{minutes} min</option>
            ))}
          </select>
        </label>
        <label>
          Site
          <input
            maxLength={255}
            value={site}
            onChange={(event) => setSite(event.target.value)}
            placeholder="Optional"
            disabled={disabled || busy}
          />
        </label>
        <label>
          Location
          <input
            maxLength={255}
            value={location}
            onChange={(event) => setLocation(event.target.value)}
            placeholder="Floor / room (optional)"
            disabled={disabled || busy}
          />
        </label>
      </div>
      <label>
        Observed symptoms or test context
        <textarea
          maxLength={2000}
          rows={2}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Optional notes"
          disabled={disabled || busy}
        />
      </label>
      <div className="collection-start-actions">
        <small>Capture profile: Wi-Fi deep dive</small>
        <button type="submit" disabled={disabled || busy}>
          {busy ? "Starting…" : "Start collection"}
        </button>
      </div>
    </form>
  );
}
