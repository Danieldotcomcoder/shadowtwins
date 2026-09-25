import { fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { ShadowTwinsReplay } from "../../api/types";
import { ChecksList, Layers2D, PairMatrix, ScoreArithmetic, SilhouetteGrid } from "./panels";
import { createViewStore, ViewStoreContext } from "./store";

const fx = (name: string) =>
  JSON.parse(readFileSync(join(__dirname, `../../../../contracts/fixtures/replays/${name}.json`), "utf-8")) as ShadowTwinsReplay;

describe("silhouette panel", () => {
  it("draws exactly the evaluator mask and marks mismatches", () => {
    const r = fx("fx-shadow-gate__silhouette-changed");
    const { container } = render(
      <SilhouetteGrid axis="x" rows={r.model!.final!.silhouettes.x} mismatch={r.model!.silhouette_mismatch!.x} caption="Model" />,
    );
    const filled = [...container.querySelectorAll("rect[fill='#cfd6e2']")].length;
    const expected = r.model!.final!.silhouettes.x.flat().filter((v) => v === 1).length;
    expect(filled).toBe(expected);
    expect(container.querySelectorAll("text").length).toBe(1); // one changed pixel: (y=1, z=1)
    expect(screen.getByText(/Lost pixels: y=1,z=1/)).toBeInTheDocument();
  });
});

describe("pair matrix", () => {
  it("labels every pair with its before/after status and selects on click", () => {
    const r = fx("fx-shadow-gate__optimal");
    const store = createViewStore();
    render(
      <ViewStoreContext.Provider value={store}>
        <PairMatrix entrances={r.entrances} original={r.original} outcome={r.model} title="Model" />
      </ViewStoreContext.Provider>,
    );
    const ab = screen.getByRole("button", { name: /A–B: originally linked; closed → not linked/ });
    const bc = screen.getByRole("button", { name: /B–C: originally not linked; opened → linked/ });
    expect(screen.getByRole("button", { name: /A–C: originally not linked; unchanged → not linked/ })).toBeInTheDocument();
    fireEvent.click(bc);
    expect(store.get().selectedPair).toEqual([1, 2]);
    expect(bc).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(ab);
    expect(store.get().selectedPair).toEqual([0, 1]);
  });

  it("never shows pair changes for invalid answers", () => {
    const r = fx("fx-shadow-gate__silhouette-changed");
    render(
      <ViewStoreContext.Provider value={createViewStore()}>
        <PairMatrix entrances={r.entrances} original={r.original} outcome={r.model} title="Model" />
      </ViewStoreContext.Provider>,
    );
    expect(screen.queryAllByRole("button", { name: /opened|closed/ })).toHaveLength(0);
    expect(screen.getByText(/Invalid answers change no pairs/)).toBeInTheDocument();
  });
});

describe("checks and arithmetic", () => {
  it("shows the evaluator's failing check and zero score for invalid answers", () => {
    const r = fx("fx-shadow-gate__silhouette-changed");
    render(<><ChecksList checks={r.model!.checks} /><ScoreArithmetic outcome={r.model!} /></>);
    expect(screen.getByText("Shadow along x unchanged")).toBeInTheDocument();
    expect(screen.getByText(/— fail/)).toBeInTheDocument();
    expect(screen.getByText("Invalid answers score")).toBeInTheDocument();
  });

  it("shows 100 × v ÷ v* for valid answers", () => {
    const r = fx("fx-shadow-gate__partial");
    render(<ScoreArithmetic outcome={r.model!} verified />);
    expect(screen.getByText(/100 × 1 ÷ 2 =/)).toBeInTheDocument();
    expect(screen.getByText("50.0")).toBeInTheDocument();
    expect(screen.getByText(/independently verified/)).toBeInTheDocument();
  });
});

describe("2D layers fallback", () => {
  it("renders all 64 cells with entrances, removed and added cells", () => {
    const r = fx("fx-shadow-gate__optimal");
    const { container } = render(
      <Layers2D state={r.model!.final} entrances={r.entrances} editable={r.editable} outcome={r.model} />,
    );
    expect(container.querySelectorAll(".lc")).toHaveLength(64);
    expect(container.querySelectorAll(".lc.removed")).toHaveLength(1);
    expect(container.querySelectorAll(".lc.added")).toHaveLength(1);
    expect(screen.getAllByText("A").length).toBeGreaterThan(0);
  });

  it("explains when no object can be built", () => {
    render(<Layers2D state={null} entrances={[]} editable={[]} />);
    expect(screen.getByText(/No object could be built/)).toBeInTheDocument();
  });

  it("lets a practice editor toggle only editable cells", () => {
    const r = fx("fx-shadow-gate__noop");
    const clicked: number[] = [];
    render(<Layers2D state={r.original} entrances={r.entrances} editable={r.editable} onCellClick={(id) => clicked.push(id)} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(r.editable.length);
    fireEvent.click(buttons[0]);
    expect(clicked).toHaveLength(1);
  });
});
