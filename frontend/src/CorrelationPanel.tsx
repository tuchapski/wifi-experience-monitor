import type { CorrelationAssessment } from "./types";

function title(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, character => character.toUpperCase());
}

export default function CorrelationPanel({ correlation }: { correlation?: CorrelationAssessment | null }) {
  if (!correlation) {
    return <section className="panel"><h2>Evidence correlation</h2>
      <p className="metric-note">No correlation assessment is stored in this sample.</p></section>;
  }

  return <section className="panel" aria-labelledby="correlation-title">
    <h2 id="correlation-title">Evidence correlation</h2>
    <p className="metric-note">Deterministic correlation of current findings, rolling SLOs,
      adaptive baseline and connection-cycle evidence. This is domain localization, not proof of root cause.</p>
    <div className="diagnostic-overview">
      <div><span>Correlation status</span><strong>{title(correlation.status)}</strong></div>
      <div><span>Correlated probable domain</span><strong>
        {correlation.primary_domain ? title(correlation.primary_domain) : "Not uniquely localized"}
      </strong></div>
      <div><span>Policy</span><strong>{correlation.policy_version}</strong></div>
    </div>
    <p className="metric-note">{correlation.reason}</p>
    {correlation.hypotheses.length > 0 && <div className="table-wrapper"><table>
      <thead><tr><th>Domain</th><th>Support</th><th>Evidence</th></tr></thead>
      <tbody>{correlation.hypotheses.map(hypothesis => <tr key={hypothesis.domain}>
        <td><strong>{hypothesis.label}</strong></td>
        <td>{hypothesis.support.toUpperCase()}</td>
        <td><ul>{hypothesis.evidence.map(item => <li key={`${hypothesis.domain}-${item.code}-${item.source}`}>
          <strong>{title(item.source)}</strong> · {item.code} — {item.message}
        </li>)}</ul>
        {hypothesis.limitations.map(item => <p className="metric-note" key={item}>{item}</p>)}</td>
      </tr>)}</tbody>
    </table></div>}
    {correlation.limitations.length > 0 && <details>
      <summary>Interpretation limits</summary>
      <ul className="metric-note">{correlation.limitations.map(item => <li key={item}>{item}</li>)}</ul>
    </details>}
  </section>;
}
