import type {
  AgentCurrentState,
  AgentSummary,
  TelemetryPoint,
} from "./agentTypes";

const API_ROOT = import.meta.env.VITE_SERVER_API_URL ?? "/api/v1";

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    let detail = `API request failed: ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // Response had no JSON body.
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

async function requestOptional<T>(path: string): Promise<T | null> {
  const response = await fetch(`${API_ROOT}${path}`, {
    headers: {
      Accept: "application/json",
    },
  });

  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getAgents(): Promise<AgentSummary[]> {
  return request<AgentSummary[]>("/agents");
}

export function getAgent(agentId: string): Promise<AgentSummary> {
  return request<AgentSummary>(`/agents/${encodeURIComponent(agentId)}`);
}

export function getAgentState(agentId: string): Promise<AgentCurrentState | null> {
  return requestOptional<AgentCurrentState>(
    `/agents/${encodeURIComponent(agentId)}/state`,
  );
}

export function getAgentTelemetry(
  agentId: string,
  metric: string,
  hours: number,
): Promise<TelemetryPoint[]> {
  const params = new URLSearchParams({
    metric,
    hours: String(hours),
    limit: "10000",
  });
  return request<TelemetryPoint[]>(
    `/agents/${encodeURIComponent(agentId)}/telemetry?${params.toString()}`,
  );
}
