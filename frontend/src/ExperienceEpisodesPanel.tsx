import type { ExperienceEpisodeHistory } from "./types";

function date(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "Ongoing";
}

function duration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "Unavailable";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${remainder}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

export default function ExperienceEpisodesPanel({
  history,
}: {
  history: ExperienceEpisodeHistory | null;
}) {
  return (
    <section className="panel" aria-labelledby="experience-episodes-title">
      <h2 id="experience-episodes-title">Experience Episodes</h2>
      <p className="metric-note">
        Incidents whose intervals overlap or are separated by no more than {history?.merge_gap_seconds ?? 120} seconds
        are grouped into one operational episode. Correlation is assigned only when stored correlated snapshots
        inside the episode agree on a single domain.
      </p>
      {!history || history.episodes.length === 0 ? (
        <div className="empty-state">No experience episodes are available.</div>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Status</th><th>Severity</th><th>Correlated domain</th><th>Incidents</th>
                <th>Started</th><th>Ended</th><th>Duration</th>
              </tr>
            </thead>
            <tbody>{history.episodes.map((episode) => (
              <tr key={episode.episode_id}>
                <td>{episode.status}</td>
                <td><strong className={`status-${episode.severity}`}>{episode.severity}</strong></td>
                <td>
                  {episode.primary_domain ?? episode.correlation_status}
                  <br /><small>{episode.correlation_sample_count} correlated snapshot(s)</small>
                </td>
                <td>
                  <strong>{episode.incident_count}</strong>
                  <details>
                    <summary>Evidence</summary>
                    <small>
                      Codes: {episode.codes.join(", ")}<br />
                      Domains: {episode.domains.join(", ")}<br />
                      Correlation: {episode.correlation_reason}
                    </small>
                  </details>
                </td>
                <td>{date(episode.started_at)}</td>
                <td>{date(episode.ended_at)}</td>
                <td>{duration(episode.duration_seconds)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}
