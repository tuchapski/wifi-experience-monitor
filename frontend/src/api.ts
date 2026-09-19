import type {
  HistoryRecord,
  SensorSnapshot,
} from "./types";


const API_URL =
  import.meta.env.VITE_API_URL ??
  "http://127.0.0.1:8000";


async function request<T>(
  path: string,
): Promise<T> {
  const response = await fetch(
    `${API_URL}${path}`,
  );

  if (!response.ok) {
    throw new Error(
      `API request failed: ${response.status}`,
    );
  }

  return response.json() as Promise<T>;
}


export function getLatestSnapshot(): Promise<SensorSnapshot> {
  return request<SensorSnapshot>(
    "/snapshot/latest",
  );
}


export function getHistory(
  limit = 100,
): Promise<HistoryRecord[]> {
  return request<HistoryRecord[]>(
    `/history?limit=${limit}`,
  );
}
