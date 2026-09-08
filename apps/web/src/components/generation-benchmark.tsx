"use client";

import { Fragment, useState } from "react";

import { benchmarkMethodology, benchmarkRuns, compareTime, elapsedSeconds, formatTime, generationSeconds } from "./generation-benchmark-data";
import styles from "./generation-benchmark.module.css";

export function GenerationBenchmark() {
  const [expanded, setExpanded] = useState<string | null>(null);

  return <section className={styles.benchmark} id="benchmark" aria-labelledby="benchmark-heading">
    <header className={styles.heading}>
      <h2 id="benchmark-heading">Video production benchmark</h2>
      <p>See the time behind the finished video. Compare successful generation time with manual production baselines.</p>
    </header>
    <p className={styles.disclosure} id="benchmark-disclosure">
      <strong>Successful attempts only.</strong> Failed attempts and waiting are excluded. Short reused saved work. Presentation uses a creator-reported measured manual average; other baselines and the 5-minute review allowance are estimates, not a measured labor-saving study.
    </p>
    <p className={styles.scrollHint}>Scroll the table sideways to compare times.</p>
    <div className={styles.tableScroll} role="region" aria-label="Scrollable benchmark comparison" tabIndex={0}>
      <table aria-describedby="benchmark-disclosure">
        <caption>Generation time and estimated manual comparison</caption>
        <thead><tr>
          <th scope="col">Video format</th>
          <th scope="col">Generation<span>Successful attempt only</span></th>
          <th scope="col">Manual workflow<span>Reported average or estimate</span></th>
          <th scope="col">Veyframe total<span>Job + 5m brief/review estimate</span></th>
          <th scope="col">Time difference<span>Estimated, not guaranteed</span></th>
        </tr></thead>
        <tbody>{benchmarkRuns.map((run) => {
          const recordedElapsed = elapsedSeconds(run);
          const generation = generationSeconds(run);
          const estimatedGeneration = recordedElapsed === null && generation !== null;
          const comparison = compareTime(generation, run.manualMinutes);
          const open = expanded === run.id;
          return <Fragment key={run.id}>
            <tr>
              <th scope="row"><button type="button" className={styles.expand}
                aria-label={`${run.label} details`} aria-expanded={open} aria-controls={`benchmark-${run.id}`}
                onClick={() => setExpanded(open ? null : run.id)}><span aria-hidden="true">{open ? "−" : "+"}</span> {run.label}</button>
                <span>{run.outputSeconds}-second video</span></th>
              <td className={styles.number}>{generation === null ? <>Not measured<span>No matched timing record</span></> : <>{formatTime(generation)}<span>{estimatedGeneration ? "Creator-measured · reported" : run.id === "short" ? "Resumed attempt · cached work" : "Fresh successful attempt"}</span></>}</td>
              <td className={styles.number}>{run.manualMinutes} min<span>{run.manualBasis}</span></td>
              <td className={styles.number}>{comparison ? <>{formatTime(comparison.totalSeconds)}<span>Includes estimated human time</span></> : "Not available"}</td>
              <td className={styles.difference}>
                {comparison ? <><strong>{comparison.savedSeconds === 0 ? "No time difference" : `${formatTime(comparison.savedSeconds)} ${comparison.savedSeconds > 0 ? "less" : "longer"}`}</strong>
                  <span>{Math.abs(comparison.savedPercent)}% {comparison.savedSeconds >= 0 ? "reduction" : "increase"} · estimate</span></> : "Not available"}
              </td>
            </tr>
            <tr hidden={!open} id={`benchmark-${run.id}`}><td colSpan={5} className={styles.detailCell}>
              {open && <div role="region" aria-label={`${run.label} methodology`} className={styles.details}>
                <div><h3>{estimatedGeneration ? "Creator measurement" : generation === null ? "Timing availability" : "Recorded job"}</h3><p>{run.project ? `${run.project}. ` : ""}{run.note}</p>
                  {run.startedAt && run.completedAt && <dl><dt>Attempt started (UTC)</dt><dd>{run.startedAt.replace("T", " ").slice(0, 19)}</dd>
                    <dt>Attempt completed (UTC)</dt><dd>{run.completedAt.replace("T", " ").slice(0, 19)}</dd>
                    <dt>Recorded attempts</dt><dd>{run.attempts} attempts · successful attempt · failed retries and waiting excluded</dd></dl>}
                </div>
                <div><h3>Manual baseline and estimated stages</h3>
                  <ul>{run.manualSteps.map((step) => <li key={step.label}><span>{step.label}</span><strong>{step.minutes} min</strong></li>)}</ul>
                  <p>{run.manualBasis}: {run.manualMinutes} minutes. Stage allocations are estimates.</p>
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
      <p>Veyframe total = recorded or creator-reported measured generation time + 5 estimated minutes for a prepared brief and final review. Estimated time difference = manual estimate − Veyframe total. Percentage reduction = time difference ÷ manual estimate. This is an elapsed-time comparison, not a measurement of hands-on work saved.</p>
      <p>These are selected examples, not averages or a speed guarantee. Timing depends on the website, narration, retries, service load and output format. Product Demo uses a user-provided 5-minute 16-second measured generation time rather than a matched completed-job record.</p>
    </details>
  </section>;
}
