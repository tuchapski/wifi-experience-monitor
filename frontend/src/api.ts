import type {
  HistoryRecord,
  HistoryWindow,
  IncidentRecord,
  SensorConfiguration,
  SensorSnapshot,
  SensorStatus,
  WirelessInterface,
} from "./types";


const API_URL =
  import.meta.env.VITE_API_URL ??
  "http://127.0.0.1:8000";


async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(
    `${API_URL}${path}`,
    {
      ...options,

      headers: {
        "Content-Type":
          "application/json",

        ...options?.headers,
      },
    },
  );

  if (!response.ok) {
    let detail =
      `API request failed: ${response.status}`;

    try {
      const body =
        await response.json() as {
          detail?: string;
        };

      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // Response had no JSON body.
    }

    throw new Error(
      detail,
    );
  }

  return response.json() as Promise<T>;
}


export function getWirelessInterfaces(
): Promise<WirelessInterface[]> {
  return request<
    WirelessInterface[]
  >(
    "/interfaces",
  );
}


export function getSensorConfiguration(
): Promise<SensorConfiguration> {
  return request<
    SensorConfiguration
  >(
    "/config",
  );
}


export function configureSensor(
  interfaceName: string,
  intervalSeconds: number,
): Promise<SensorConfiguration> {
  return request<
    SensorConfiguration
  >(
    "/config",
    {
      method: "PUT",

      body: JSON.stringify({
        interface: interfaceName,

        interval_seconds:
          intervalSeconds,
      }),
    },
  );
}


export function getSensorStatus(
): Promise<SensorStatus> {
  return request<SensorStatus>(
    "/sensor/status",
  );
}


export function startSensor(
): Promise<SensorStatus> {
  return request<SensorStatus>(
    "/sensor/start",
    {
      method: "POST",
    },
  );
}


export function stopSensor(
): Promise<SensorStatus> {
  return request<SensorStatus>(
    "/sensor/stop",
    {
      method: "POST",
    },
  );
}


export async function getLatestSnapshot(
): Promise<SensorSnapshot | null> {
  const response = await fetch(
    `${API_URL}/snapshot/latest`,
  );

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(
      `API request failed: ${response.status}`,
    );
  }

  return response.json() as Promise<
    SensorSnapshot
  >;
}


export function getHistory(
  limit = 100,
): Promise<HistoryRecord[]> {
  return request<HistoryRecord[]>(
    `/history?limit=${limit}`,
  );
}


export function getActiveIncidents(
): Promise<IncidentRecord[]> {
  return request<IncidentRecord[]>(
    "/incidents/active",
  );
}


export function getIncidentHistory(
  limit = 100,
): Promise<IncidentRecord[]> {
  return request<IncidentRecord[]>(
    `/incidents/history?limit=${limit}`,
  );
}


export function getHistoryInterfaces(): Promise<string[]> {
  return request<string[]>("/history/interfaces");
}

export function getHistoryWindow(
  interfaceName: string, start: string, end: string, signal?: AbortSignal,
): Promise<HistoryWindow> {
  const query = new URLSearchParams({ interface: interfaceName, start, end, max_points: "600" });
  query.set("compare", "true");
  return request<HistoryWindow>(`/history/window?${query}`, { signal });
}

export function getReportUrl(interfaceName: string, start: string, end: string): string {
  const query = new URLSearchParams({ interface: interfaceName, start, end });
  return `${API_URL}/reports/html?${query}`;
}
