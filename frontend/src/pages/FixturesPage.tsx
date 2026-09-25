import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { ShadowTwinsReplay } from "../api/types";
import { Comparison } from "../components/inspect/Comparison";
import { Empty, Loading } from "../components/ui/ui";
import { useDocumentTitle } from "../lib/hooks";
import { categoryLabel } from "../lib/labels";
import { EvidencePanels } from "./InstancePage";

interface FixtureIndex {
  responses: { case: string; instance_id: string; valid: boolean; category: string | null; score: number; replay: string }[];
}

const REPLAYS = import.meta.glob("../../../contracts/fixtures/replays/*.json", { import: "default" });
const INDEX = import.meta.glob("../../../contracts/fixtures/index.json", { import: "default", eager: true });

export function FixturesPage() {
  useDocumentTitle("Fixture gallery");
  const index = Object.values(INDEX)[0] as FixtureIndex | undefined;
  const [sel, setSel] = useState(index?.responses.find((r) => r.case === "partial")?.replay ?? index?.responses[0]?.replay);
  const replay = useQuery({
    queryKey: ["fixture", sel],
    enabled: !!sel,
    queryFn: async () => {
      const key = `../../../contracts/fixtures/${sel}`;
      const load = REPLAYS[key];
      if (!load) throw new Error(`fixture ${sel} not bundled`);
      return (await load()) as ShadowTwinsReplay;
    },
  });
  if (!index) return <Empty title="No fixtures bundled" />;
  return (
    <div className="stack fade-in">
      <div className="page-head">
        <div>
          <h1>Fixture gallery</h1>
          <p>Hand-checked formal fixtures with sample answers covering every answer category. These are test material
            for the rules and the viewer — <strong>not model results</strong>.</p>
        </div>
      </div>
      <div className="fixture-chips" role="listbox" aria-label="Fixture cases">
        {index.responses.map((r) => (
          <button key={r.replay} type="button" role="option" aria-selected={sel === r.replay}
            className={`chip${sel === r.replay ? " on" : ""}`} onClick={() => setSel(r.replay)}>
            <span className={r.valid ? "ok-text" : "bad-text"}>{r.valid ? "✓" : "✕"}</span> {r.case}
            <span className="xsmall faint"> · {r.valid ? r.score.toFixed(0) : categoryLabel(r.category)}</span>
          </button>
        ))}
      </div>
      {replay.isLoading && <Loading />}
      {replay.data && (
        <>
          <Comparison replay={replay.data} modelLabel="Sample answer"
            note={<>Formal fixture <span className="mono">{replay.data.instance_id}</span> with a hand-written sample answer. Not a model result.</>} />
          <EvidencePanels replay={replay.data} />
        </>
      )}
    </div>
  );
}
