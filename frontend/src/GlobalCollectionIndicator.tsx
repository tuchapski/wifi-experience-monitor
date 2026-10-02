import { useEffect, useState } from "react";

import { getAgentRecordings } from "./agentApi";
import { diagnosticsAgentHash } from "./diagnosticRoutes";
import "./GlobalCollectionIndicator.css";

const ACTIVE_STATUSES = new Set(["created", "recording", "stopping"]);

export default function GlobalCollectionIndicator({ agentId }: { agentId: string | null }) {
  const [activity, setActivity] = useState<{ agentId: string; count: number } | null>(null);
  const activeCount = activity?.agentId === agentId ? activity?.count ?? 0 : 0;

  useEffect(() => {
    if (!agentId) return;
    const currentAgentId = agentId;
    let mounted = true;

    async function refresh(): Promise<void> {
      try {
        const recordings = await getAgentRecordings(currentAgentId);
        if (!mounted) return;
        setActivity({ agentId: currentAgentId, count: recordings.filter((recording) =>
          !recording.project_run_id && ACTIVE_STATUSES.has(recording.status)).length });
      } catch {
        // Keep the last known count when the global activity refresh fails.
      }
    }

    void refresh();
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [agentId]);

  if (!agentId || activeCount === 0) return null;

  function openActivity(): void {
    if (!agentId) return;
    window.location.hash = diagnosticsAgentHash(agentId);
    window.setTimeout(() => {
      document.getElementById("diagnostics-now-collecting")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 100);
  }

  return (
    <button
      type="button"
      className="global-collection-indicator"
      onClick={openActivity}
      aria-label={`${activeCount} active collection${activeCount === 1 ? "" : "s"}. Open collection activity.`}
    >
      <i aria-hidden="true" />
      <span>{activeCount} collecting</span>
    </button>
  );
}
