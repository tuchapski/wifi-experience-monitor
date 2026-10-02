import type { ClientEpisode } from "./agentTypes";

export function episodeStatus(episode: ClientEpisode, now: number): string {
  if (!episode.closed_at && now - Date.parse(episode.last_observed_at) > 30_000) return "unknown";
  return episode.status;
}
