import { Link } from "react-router-dom";
import { usePractice } from "../api/hooks";
import { Empty, ErrorBox, Loading } from "../components/ui/ui";
import { useDocumentTitle } from "../lib/hooks";
import { TIER_NAME } from "../lib/labels";

export function PracticeListPage() {
  useDocumentTitle("Practice");
  const list = usePractice();
  return (
    <div className="stack fade-in">
      <div className="page-head">
        <div>
          <h1>Practice</h1>
          <p>
            Solve the same kind of puzzle the models get. These nine practice instances are separate from the ranked
            pack, and your answers are never ranked. The server scores every submission exactly.
          </p>
        </div>
      </div>
      {list.isLoading && <Loading />}
      {list.error && <ErrorBox error={list.error} />}
      {list.data && list.data.length === 0 && <div className="card"><Empty title="No practice pack is loaded" /></div>}
      <div className="practice-grid">
        {list.data?.map((p, k) => (
          <Link key={p.instance_id} to={`/practice/${encodeURIComponent(p.instance_id)}`} className="card card-pad practice-card">
            <div className="spread"><strong>Puzzle {k + 1}</strong><span className="badge">{p.tier}</span></div>
            <div className="small dim">{TIER_NAME[p.tier] ?? p.tier}</div>
            <div className="row xsmall faint">
              <span>{p.budget} move{p.budget === 1 ? "" : "s"}</span>·<span>{p.entrances} entrances</span>·<span>{p.editable} editable</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
