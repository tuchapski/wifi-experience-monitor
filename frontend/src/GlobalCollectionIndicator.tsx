import { useEffect, useState } from "react";

import { getAgentRecordings, getAgents } from "./agentApi";
import "./GlobalCollectionIndicator.css";

const ACTIVE_STATUSES = new Set(["created", "recording", "stopping"]);

export default function GlobalCollectionIndicator() {
  const [activeCount, setActiveCount] = useState(0);

  useEffect(() => {
    let mounted = true;

    async function refresh(): Promise<void> {
      try {
        const agents = await getAgents();
        const results = await Promise.allSettled(
          agents.map(async (agent) => {
            const recordings = await getAgentRecordings(agent.id);
            return recordings.filter((recording) => ACTIVE_STATUSES.has(recording.status)).length;
          }),
        );

        if (!mounted || results.some((result) => result.status === "rejected")) return;

        setActiveCount(
          results.reduce(
            (total, result) => total + (result.status === "fulfilled" ? result.value : 0),
            0,
          ),
        );
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
  }, []);

  if (activeCount === 0) return null;

  function openActivity(): void {
    window.location.hash = "#diagnostics";
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
