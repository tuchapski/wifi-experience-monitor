export interface WorkspaceRoute {
  section: "agents" | "diagnostics";
  agentId: string | null;
  recordingId: string | null;
  episodeId?: string;
}

export function diagnosticsAgentHash(agentId: string): string {
  return `#diagnostics/agents/${encodeURIComponent(agentId)}`;
}

export function diagnosticsRecordingHash(agentId: string, recordingId: string): string {
  return `${diagnosticsAgentHash(agentId)}/recordings/${encodeURIComponent(recordingId)}`;
}

export function clientEpisodeHash(agentId: string, episodeId: string): string {
  return `#agents/${encodeURIComponent(agentId)}/episodes/${encodeURIComponent(episodeId)}`;
}

export function parseWorkspaceRoute(hash: string): WorkspaceRoute {
  const episodeMatch = hash.match(/^#agents\/([^/]+)\/episodes\/([^/]+)$/);
  if (episodeMatch) return { section: "agents", agentId: decodeURIComponent(episodeMatch[1]), recordingId: null, episodeId: decodeURIComponent(episodeMatch[2]) };
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
