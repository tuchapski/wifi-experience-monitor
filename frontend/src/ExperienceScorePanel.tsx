import type { ExperienceScore } from "./types";

function number(value: number | null, suffix = "") {
  return value == null || !Number.isFinite(value) ? "Unavailable"
    : value.toLocaleString(undefined, { maximumFractionDigits: 2 }) + suffix;
}

export default function ExperienceScorePanel({ score }: { score?: ExperienceScore | null }) {
  if (!score) {
    return <section className="panel" aria-labelledby="experience-score-title">
      <h2 id="experience-score-title">Experience score</h2>
      <p className="metric-note">This sample has no score. New samples from the updated sensor
        include the scoring policy and evidence; old history is not recalculated.</p>
    </section>;
  }
  const labels = {
    complete: "Complete assessment",
    partial: "Provisional · incomplete assessment",
    unavailable: "Insufficient evidence",
  };
  const failures = score.components.filter(part => part.metrics.some(item => item.state === "failed"));
  return <section className="panel experience-score" aria-labelledby="experience-score-title">
    <div className="score-heading">
      <div>
        <h2 id="experience-score-title">Experience score</h2>
        <p className="metric-note">{labels[score.status]} · policy {score.policy_version}</p>
      </div>
      <strong className="score-value">{number(score.value)}
        {score.value != null && <small> / 100</small>}
      </strong>
    </div>
    <div className="score-coverage">
      <label htmlFor="score-coverage">Evidence coverage: {number(score.coverage_percent, "%")}</label>
      <progress id="score-coverage" max={100} value={score.coverage_percent}>
        {number(score.coverage_percent, "%")}
      </progress>
    </div>
    <p className="metric-note">Coverage is the available share of configured evidence weights,
      not a statistical confidence level. A complete assessment does not mean every test passed.</p>
    {failures.length > 0 && <p className="score-failure">
      Confirmed test/association failure: {failures.map(part => part.label).join(", ")}.
      The weighted average does not override these failures or the diagnostic findings.
    </p>}
    <ul className="metric-note">{score.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>
    <div className="table-wrapper">
      <table>
        <caption>Component scores and contribution to the global score</caption>
        <thead><tr>
          <th scope="col">Component</th><th scope="col">Base weight</th>
          <th scope="col">Coverage</th><th scope="col">Effective weight*</th>
          <th scope="col">Score / 100</th><th scope="col">Points added</th>
          <th scope="col">Points deducted</th>
        </tr></thead>
        <tbody>{score.components.map(part => <tr key={part.key}>
          <th scope="row">{part.label}</th>
          <td>{number(part.weight, "%")}</td><td>{number(part.coverage_percent, "%")}</td>
          <td>{number(part.effective_weight, "%")}</td><td>{number(part.score)}</td>
          <td>{number(part.contribution)}</td><td>{number(part.deduction)}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <p className="metric-note">*Effective weights are renormalized over available evidence.
      Global score = Σ(component score × effective weight) / 100.
      Coverage = Σ(base weight × component coverage) / 100.
      Contributions are withheld when the global score is unavailable; displayed rounding
      can cause small differences in sums. No RF survey support is required.</p>
    <details>
      <summary>Explain measurements, penalties and thresholds</summary>
      {score.components.map(part => <section className="score-evidence" key={part.key}>
        <h3>{part.label}</h3>
        <p className="metric-note">Scope: {part.scope === "host"
          ? "Host route · not bound to the selected Wi-Fi interface" : part.scope}.
          Metric weights below apply within this component.</p>
        <ul>{part.metrics.map(item => <li key={item.key}>
          <strong>{item.label}</strong> · weight {number(item.weight, "%")} · {item.state}
          <br />Reading: {number(item.value, ` ${item.unit}`)} · score: {number(item.score)}
          <br />{item.reason}
          <p className="metric-note">{item.rule}</p>
        </li>)}</ul>
      </section>)}
    </details>
  </section>;
}
