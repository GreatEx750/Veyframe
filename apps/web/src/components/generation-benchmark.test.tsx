import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { GenerationBenchmark } from "./generation-benchmark";
import { benchmarkRuns, compareTime, elapsedSeconds } from "./generation-benchmark-data";

afterEach(cleanup);

describe("generation benchmark evidence and estimates", () => {
  it("uses full saved job windows, including retry gaps, without claiming a population average", () => {
    expect(benchmarkRuns.map(elapsedSeconds)).toEqual([null, 1628, 142, 401]);
    expect(benchmarkRuns.map((run) => run.attempts)).toEqual([null, 3, 1, 2]);
    for (const run of benchmarkRuns) {
      expect(run.manualSteps.reduce((total, step) => total + step.minutes, 0)).toBe(run.manualMinutes);
    }
  });

  it("includes estimated brief/review time and reports negative savings honestly", () => {
    expect(compareTime(142, 35)).toEqual({ totalSeconds: 442, savedSeconds: 1658, savedPercent: 79 });
    expect(compareTime(1628, 5)?.savedSeconds).toBe(-1628);
    expect(compareTime(null, 30)).toBeNull();
    for (const value of [null, 0, -1, Infinity, NaN, 1441]) expect(compareTime(142, value)).toBeNull();
  });

  it("labels measurements, assumptions, sample size, and methodology", () => {
    render(<GenerationBenchmark />);
    expect(screen.getByRole("heading", { name: "Video production benchmark" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Generation time and estimated manual comparison" })).toBeInTheDocument();
    expect(screen.getByText(/selected examples, not averages/i)).toBeInTheDocument();
    expect(screen.getByText(/not a measured labor-saving study/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download timing data" })).toHaveAttribute("href", "/benchmarks/generation-2026-09-06.json");
    expect(screen.getByRole("cell", { name: "120 min" })).toBeInTheDocument();
  });

  it("lets a visitor inspect the estimated manual breakdown and recorded attempts", () => {
    render(<GenerationBenchmark />);
    fireEvent.click(screen.getByRole("button", { name: "Presentation details" }));
    expect(screen.getByRole("button", { name: "Presentation details" })).toHaveAttribute("aria-expanded", "true");
    const details = screen.getByRole("region", { name: "Presentation methodology" });
    expect(within(details).getByText(/3 attempts/i)).toBeInTheDocument();
    expect(within(details).getByText(/not the independently edited showcase/i)).toBeInTheDocument();
    expect(within(details).getByText("Edit, captions and layout")).toBeInTheDocument();
  });

  it("shows fixed manual estimates without editing or reset controls", () => {
    render(<GenerationBenchmark />);
    for (const minutes of [60, 120, 35, 45]) {
      expect(screen.getByRole("cell", { name: `${minutes} min` })).toBeInTheDocument();
    }
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reset estimates" })).not.toBeInTheDocument();
    expect(screen.queryByText(/editable|edit estimates|editing the total/i)).not.toBeInTheDocument();
    expect(screen.getByText("1h 27m 52s less")).toBeInTheDocument();
    expect(screen.getByText("27m 38s less")).toBeInTheDocument();
    expect(screen.getByText("33m 19s less")).toBeInTheDocument();
  });

  it("shows all four formats without the date toolbar or format filter", () => {
    render(<GenerationBenchmark />);
    for (const label of ["Product Demo", "Presentation", "Spotlight", "Short"]) {
      expect(screen.getByRole("button", { name: `${label} details` })).toBeInTheDocument();
    }
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByText(/6 Sep 2026|Local runs|One saved job per format/i)).not.toBeInTheDocument();
    const row = screen.getByRole("button", { name: "Product Demo details" }).closest("tr")!;
    expect(within(row).getByText("90-second video")).toBeInTheDocument();
    expect(within(row).getByText("Not measured")).toBeInTheDocument();
    expect(within(row).queryByText(/less|reduction|0m/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Product Demo details" }));
    const details = screen.getByRole("region", { name: "Product Demo methodology" });
    expect(within(details).getByText(/user-provided estimate/i)).toBeInTheDocument();
    expect(within(details).getByText("Fixed estimated total: 60 minutes.")).toBeInTheDocument();
    expect(within(details).getByText(/no matched completed generation job/i)).toBeInTheDocument();
    expect(within(details).queryByText("Job submitted (UTC)")).not.toBeInTheDocument();
  });
});
