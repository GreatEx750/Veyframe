"use client";

import { Fragment, useState } from "react";

import { benchmarkMethodology, benchmarkRuns, compareTime, elapsedSeconds, formatTime } from "./generation-benchmark-data";
import styles from "./generation-benchmark.module.css";

export function GenerationBenchmark() {
  const [expanded, setExpanded] = useState<string | null>(null);

  return <section className={styles.benchmark} id="benchmark" aria-labelledby="benchmark-heading">
    <header className={styles.heading}>
      <h2 id="benchmark-heading">Video production benchmark</h2>
      <p>See the time behind the finished video. Compare recorded Veyframe jobs with fixed manual workflow estimates.</p>
    </header>
    <p className={styles.disclosure} id="benchmark-disclosure">
      <strong>Measured generation. Estimated savings.</strong> Manual times and the 5-minute Veyframe brief/review allowance are assumptions—not a measured labor-saving study.
    </p>
    <p className={styles.scrollHint}>Scroll the table sideways to compare times.</p>
    <div className={styles.tableScroll} role="region" aria-label="Scrollable benchmark comparison" tabIndex={0}>
      <table aria-describedby="benchmark-disclosure">
        <caption>Generation time and estimated manual comparison</caption>
        <thead><tr>
          <th scope="col">Video format</th>
          <th scope="col">Generation<span>Measured job time</span></th>
          <th scope="col">Manual workflow<span>Fixed estimate</span></th>
          <th scope="col">Veyframe total<span>Job + 5m brief/review estimate</span></th>
          <th scope="col">Time difference<span>Estimated, not guaranteed</span></th>
        </tr></thead>
        <tbody>{benchmarkRuns.map((run) => {
          const elapsed = elapsedSeconds(run);
          const comparison = compareTime(elapsed, run.manualMinutes);
          const open = expanded === run.id;
          return <Fragment key={run.id}>
            <tr>
              <th scope="row"><button type="button" className={styles.expand}
                aria-label={`${run.label} details`} aria-expanded={open} aria-controls={`benchmark-${run.id}`}
                onClick={() => setExpanded(open ? null : run.id)}><span aria-hidden="true">{open ? "−" : "+"}</span> {run.label}</button>
                <span>{run.outputSeconds}-second video</span></th>
              <td className={styles.number}>{elapsed === null ? <>Not measured<span>No matched timing record</span></> : <>{formatTime(elapsed)}<span>{run.attempts} {run.attempts === 1 ? "attempt" : "attempts"} included</span></>}</td>
              <td className={styles.number}>{run.manualMinutes} min</td>
              <td className={styles.number}>{comparison ? <>{formatTime(comparison.totalSeconds)}<span>Includes estimated human time</span></> : "Not available"}</td>
              <td className={styles.difference}>
                {comparison ? <><strong>{comparison.savedSeconds === 0 ? "No time difference" : `${formatTime(comparison.savedSeconds)} ${comparison.savedSeconds > 0 ? "less" : "longer"}`}</strong>
                  <span>{Math.abs(comparison.savedPercent)}% {comparison.savedSeconds >= 0 ? "reduction" : "increase"} · estimate</span></> : "Not available"}
              </td>
            </tr>
            <tr hidden={!open} id={`benchmark-${run.id}`}><td colSpan={5} className={styles.detailCell}>
              {open && <div role="region" aria-label={`${run.label} methodology`} className={styles.details}>
                <div><h3>{elapsed === null ? "Timing availability" : "Recorded job"}</h3><p>{run.project ? `${run.project}. ` : ""}{run.note}</p>
                  {run.startedAt && run.completedAt && <dl><dt>Job submitted (UTC)</dt><dd>{run.startedAt.replace("T", " ").slice(0, 19)}</dd>
                    <dt>Completion saved (UTC)</dt><dd>{run.completedAt.replace("T", " ").slice(0, 19)}</dd>
                    <dt>Recorded attempts</dt><dd>{run.attempts} attempts · retries and gaps included</dd></dl>}
                </div>
                <div><h3>Manual estimate: starting assumptions</h3>
                  <ul>{run.manualSteps.map((step) => <li key={step.label}><span>{step.label}</span><strong>{step.minutes} min</strong></li>)}</ul>
                  <p>Fixed estimated total: {run.manualMinutes} minutes.</p>
                </div>
              </div>}
            </td></tr>
          </Fragment>;
        })}</tbody>
      </table>
    </div>
    <div className={styles.actions}>
      <a href="/benchmarks/generation-2026-09-06.json" download>Download timing data</a>
    </div>
    <details className={styles.methodology}>
      <summary>How to read these numbers</summary>
      <p>{benchmarkMethodology.timing}</p>
      <p>{benchmarkMethodology.manualMethod}</p>
      <p>{benchmarkMethodology.limitations}</p>
      <p>Veyframe total = recorded job time + 5 estimated minutes for a prepared brief and final review. Estimated time difference = manual estimate − Veyframe total. Percentage reduction = time difference ÷ manual estimate. This is an elapsed-time comparison, not a measurement of hands-on work saved.</p>
      <p>These are selected examples, not averages or a speed guarantee. Timing depends on the website, narration, retries, service load and output format. Product Demo has a manual estimate only; its generation time and savings are unavailable until a matched completed job is recorded.</p>
    </details>
  </section>;
}
