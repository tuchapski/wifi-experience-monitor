import { useEffect, useState } from "react";
import { getClientDetection } from "./agentApi";
import type { ClientDetection } from "./agentTypes";
import ClientDetectionContent from "./ClientDetectionContent";
import ExperienceProfileEditor from "./ExperienceProfileEditor";
import "./ClientDetection.css";

export default function ClientDetectionPanel({ agentId }: { agentId: string }) {
  const [data, setData] = useState<ClientDetection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    let active = true;
    let pending = false;
    let received: number | null = null;
    async function refresh() {
      if (pending) return;
      pending = true;
      try {
        const result = await getClientDetection(agentId);
        if (active) { received = performance.now(); setData(result); setError(null); setElapsed(0); }
      } catch (err) {
        if (active) { setData(null); setError(err instanceof Error ? err.message : "Unable to refresh detection"); }
      } finally { pending = false; }
    }
    void refresh();
    const poll = window.setInterval(() => void refresh(), 5000);
    const timer = window.setInterval(() => { if (received !== null) setElapsed((performance.now() - received) / 1000); }, 1000);
    return () => { active = false; window.clearInterval(poll); window.clearInterval(timer); };
  }, [agentId]);
  return <section className="agent-panel client-detector" aria-label="Continuous client detection">
    <div className="agent-panel-heading"><div><span className="agent-eyebrow">Individual client</span><h2>Continuous detection</h2><p>Observed failures, persistent objective violations and changes against comparable reference periods.</p></div></div>
    {data && data.agent_id === agentId ? <ClientDetectionContent data={data} elapsedSeconds={elapsed} />
      : <p className="detector-loading" role="status">{error ? `Detection unavailable: ${error}` : "Loading detection…"}</p>}
    <ExperienceProfileEditor key={agentId} agentId={agentId} />
  </section>;
}
