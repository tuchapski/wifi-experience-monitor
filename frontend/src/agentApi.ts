import type {
  AgentCurrentState,
  AgentSummary,
  DiagnosticRecording,
  RecordingEvent,
  RecordingMetricPoint,
  StartRecordingInput,
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

async function mutationRequest<T>(
  path: string,
  method: "POST",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    let detail = `API request failed: ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Response had no JSON body.
    }
    throw new Error(detail);
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

export function getAgentRecordings(
  agentId: string,
): Promise<DiagnosticRecording[]> {
  return request<DiagnosticRecording[]>(
    `/agents/${encodeURIComponent(agentId)}/recordings`,
  );
}

export function startAgentRecording(
  agentId: string,
  input: StartRecordingInput,
): Promise<DiagnosticRecording> {
  return mutationRequest<DiagnosticRecording>(
    `/agents/${encodeURIComponent(agentId)}/recordings`,
    "POST",
    input,
  );
}

export function stopRecording(
  recordingId: string,
): Promise<DiagnosticRecording> {
  return mutationRequest<DiagnosticRecording>(
    `/recordings/${encodeURIComponent(recordingId)}/stop`,
    "POST",
  );
}

export function getRecording(
  recordingId: string,
): Promise<DiagnosticRecording> {
  return request<DiagnosticRecording>(
    `/recordings/${encodeURIComponent(recordingId)}`,
  );
}

export function getRecordingMetrics(
  recordingId: string,
  metric: string,
  limit = 50000,
): Promise<RecordingMetricPoint[]> {
  const params = new URLSearchParams({
    metric,
    limit: String(limit),
  });
  return request<RecordingMetricPoint[]>(
    `/recordings/${encodeURIComponent(recordingId)}/metrics?${params.toString()}`,
  );
}

export function getRecordingEvents(
  recordingId: string,
  limit = 5000,
): Promise<RecordingEvent[]> {
  const params = new URLSearchParams({
    limit: String(limit),
  });
  return request<RecordingEvent[]>(
    `/recordings/${encodeURIComponent(recordingId)}/events?${params.toString()}`,
  );
}
