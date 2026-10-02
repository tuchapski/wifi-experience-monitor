import { useEffect, useState } from "react";
import { getClientExperience } from "./agentApi";
import type { ClientExperience } from "./agentTypes";
import ClientExperienceContent from "./ClientExperienceContent";
import "./ClientExperience.css";

export default function ClientExperiencePanel({ agentId }: { agentId: string }) {
  const [result, setResult] = useState<{ data: ClientExperience; receivedAt: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    let active = true;
    let pending = false;
    let receivedAt: number | null = null;
    async function refresh(): Promise<void> {
      if (pending) return;
      pending = true;
      try {
        const data = await getClientExperience(agentId);
        if (active) {
          receivedAt = performance.now();
          setResult({ data, receivedAt });
          setElapsed(0);
          setError(null);
        }
      } catch (err) {
        if (active) {
          setResult(null);
          setError(err instanceof Error ? err.message : "Unable to refresh client experience");
        }
      } finally {
        pending = false;
      }
    }
    void refresh();
    const refreshTimer = window.setInterval(() => void refresh(), 5000);
    const ageTimer = window.setInterval(() => {
      if (receivedAt !== null) setElapsed((performance.now() - receivedAt) / 1000);
    }, 1000);
    return () => {
      active = false;
      window.clearInterval(refreshTimer);
      window.clearInterval(ageTimer);
    };
  }, [agentId]);
  if (!result || result.data.agent_id !== agentId) return <section className="agent-panel client-experience">
    <div className="agent-panel-heading"><div><span className="agent-eyebrow">Individual client experience</span><h2>Experience now</h2></div></div>
    <p className="client-experience-loading" role="status">{error ? `Experience unavailable: ${error}` : "Loading current evidence…"}</p>
  </section>;
  return <ClientExperienceContent data={result.data} elapsedSeconds={elapsed} />;
}
