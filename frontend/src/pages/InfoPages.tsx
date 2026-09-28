import { Fragment } from "react";
import { Link } from "react-router-dom";
import { useMeta } from "../api/hooks";
import { Empty } from "../components/ui/ui";
import { useDocumentTitle } from "../lib/hooks";

export function AboutPage() {
  useDocumentTitle("Method");
  const meta = useMeta();
  const versions = meta.data?.benchmarks?.[0]?.versions as Record<string, string> | undefined;
  return (
    <div className="stack fade-in prose">
      <div className="page-head">
        <div>
          <h1>How Shadow Twins works</h1>
          <p>
            A compact, text-only spatial optimization task with exactly verified optimal answers. The 3D views are for
            people; models only ever receive a short text description.
          </p>
        </div>
      </div>
      <div className="grid-2">
        <section className="card card-pad stack-s">
          <h2>The task</h2>
          <p>A model sees a 4×4×4 voxel object as four binary layers, a few marked tunnel entrances on the surface, and a list of
            editable cells with IDs. It may relocate at most <em>b</em> (1–3) cubes, answering with JSON like
            <code> {`{"remove":[2],"add":[7]}`}</code>.</p>
          <p>The result must keep <strong>all three orthographic shadows</strong> identical, change only editable cells, and keep the
            solid in one face-connected piece. The goal is to change the linked/unlinked status of as many entrance pairs as
            possible — opening and closing routes count equally. Empty cells connect only through shared faces inside the grid.</p>
        </section>
        <section className="card card-pad stack-s">
          <h2>Scoring</h2>
          <p><strong>score = 100 × v ÷ v*</strong>, where <em>v</em> counts changed entrance pairs and <em>v*</em> is the maximum over
            every legal edit, found by exhaustive enumeration and reproduced by an independent verifier. Invalid answers score 0 with
            a specific category; a valid no-op also scores 0 but stays distinguishable. No LLM judges, no renderer-derived scores,
            no move-efficiency bonus.</p>
          <p>Repetitions are averaged per instance, instances per tier, and the three tiers weigh equally. A run has an official score
            only when every scheduled item has an evaluated answer; transport failures are never counted as model errors.</p>
        </section>
        <section className="card card-pad stack-s">
          <h2>Packs and tiers</h2>
          <p>Instances are generated from seeds and admitted by a policy frozen before any ranked candidate was drawn: a positive
            optimum with partial credit, an active shadow constraint (shadows must reject real options) and a prompt under 800 tokens
            for every tokenizer in a frozen panel. T1 needs one relocation, T2 two coordinated relocations, T3 three — or defeats a
            local-search baseline.</p>
          <p className="small dim">Standard: 30 ranked instances. Repeated: the same 30 × 3 on a separate track. Quick Check: 9 practice
            instances, never ranked.</p>
        </section>
        <section className="card card-pad stack-s">
          <h2>Integrity</h2>
          <ul className="plain-list small">
            <li>Every ranked certificate is reproduced by an independent verifier before release.</li>
            <li>Ranked OpenRouter runs pin one provider endpoint with fallbacks disabled; the reported provider must
              match. Groq models are served by Groq itself, with no fallbacks.</li>
            <li>The leaderboard lists the latest eligible run, never the best of several.</li>
            <li>Invalid or poor answers are never retried; only transport and server failures are, with a fixed policy.</li>
            <li>Novelty is <strong>unconfirmed</strong>. The pack is public and may appear in training data; no contamination
              resistance is claimed.</li>
          </ul>
        </section>
      </div>
      {versions && (
        <section className="card card-pad">
          <h2>Frozen versions</h2>
          <dl className="kv" style={{ marginTop: 10 }}>
            {Object.entries(versions).map(([k, v]) => (
              <Fragment key={k}><dt>{k}</dt><dd className="mono small">{v}</dd></Fragment>
            ))}
          </dl>
        </section>
      )}
      <p className="small dim">Formal fixtures used to check the mathematics are browsable in the <Link to="/fixtures">fixture gallery</Link>.</p>
    </div>
  );
}

export function NotFoundPage() {
  useDocumentTitle("Not found");
  return (
    <div className="card"><Empty title="Page not found" action={<Link to="/" className="btn">Back to Evaluate</Link>}>
      That address does not match any page.</Empty></div>
  );
}
