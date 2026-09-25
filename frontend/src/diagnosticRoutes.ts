export interface WorkspaceRoute {
  section: "agents" | "diagnostics";
  agentId: string | null;
  recordingId: string | null;
}

export function diagnosticsAgentHash(agentId: string): string {
  return `#diagnostics/agents/${encodeURIComponent(agentId)}`;
}

export function diagnosticsRecordingHash(agentId: string, recordingId: string): string {
  return `${diagnosticsAgentHash(agentId)}/recordings/${encodeURIComponent(recordingId)}`;
}

export function parseWorkspaceRoute(hash: string): WorkspaceRoute {
  const recordingMatch = hash.match(
    /^#(?:agents|diagnostics\/agents)\/([^/]+)\/recordings\/([^/]+)$/,
  );
  if (recordingMatch) {
    return {
      section: "diagnostics",
      agentId: decodeURIComponent(recordingMatch[1]),
      recordingId: decodeURIComponent(recordingMatch[2]),
    };
  }

  const diagnosticsAgent = hash.match(/^#diagnostics\/agents\/([^/]+)$/);
  if (diagnosticsAgent) {
    return {
      section: "diagnostics",
      agentId: decodeURIComponent(diagnosticsAgent[1]),
      recordingId: null,
    };
  }
  if (hash === "#diagnostics") {
    return { section: "diagnostics", agentId: null, recordingId: null };
  }

  const agentMatch = hash.match(/^#agents\/([^/]+)$/);
  return {
    section: "agents",
    agentId: agentMatch ? decodeURIComponent(agentMatch[1]) : null,
    recordingId: null,
  };
}
