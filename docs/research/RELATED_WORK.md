# Related work and originality assessment

Owner: P2 (P5 appends pilot findings). Status: **novelty unconfirmed.** This is a scoped,
incomplete search performed on 2026-09-25/26 from public project pages and search results; it is
not a systematic review. Nothing below claims that Shadow Twins is the first benchmark of its kind.

## What Shadow Twins measures

A text-only model receives a full 4×4×4 voxel object, marked tunnel entrances and a small list of
editable cells. It relocates at most `b ≤ 3` cubes to change as many entrance-pair connectivity
relations as possible, while keeping all three binary orthographic silhouettes identical and the
solid face-connected. Scores are exact (`100·v/v*`) against an exhaustively certified optimum.

## Closest work

| Work | What it is | Overlap | Distinction |
|---|---|---|---|
| **Shadow Art** — Mitra & Pauly, ACM SIGGRAPH Asia 2009 ([project page](https://graphics.stanford.edu/~niloy/research/shadowArt/shadowArt_sigA_09.html)) | Graphics method: from user-given binary shadow images and projection setups, optimize a voxel "shadow volume" whose shadows best approximate the images; notes that shadow images often contradict each other and provides editing tools that respect shadow constraints | Voxel objects constrained by multiple binary projections; editing under shadow constraints | Shadow Art is a design/optimization algorithm, not an evaluation of models. It targets approximating given shadows; Shadow Twins holds shadows fixed exactly and scores an *internal connectivity* objective with a certified optimum |
| **CHAIN** — Lan et al., 2026, arXiv 2602.21015 ([project page](https://social-ai-studio.github.io/CHAIN/)) | Interactive 3D benchmark for vision-language (and diffusion) models: 109 levels of mechanical interlocking puzzles (e.g. Kongming/Lu Ban locks, burrs) and irregular-block stacking, scored by Pass@1 and plan efficiency | 3D structure manipulation under physical/causal constraints; action sequences | CHAIN is visual and interactive with physical contact/support; Shadow Twins is single-turn, text-only, discrete, with exact partial credit and no physics |
| **MARBLE** — Jiang, Chai, Brbić, Moor, 2025, arXiv 2506.22992 ([project page](https://marble-benchmark.github.io/)) | Multimodal spatial reasoning and planning: M-Portal (plan verification / fill-the-blank on Portal 2 maps) and M-Cube (3D jigsaw assembly into a cube), scored by F1/accuracy | Multi-step spatial planning with constraints; cube assembly | MARBLE requires perception of images and uses correctness metrics; Shadow Twins gives full geometry as text and grades optimization quality relative to a proven optimum |
| **NPHardEval** — 2023, arXiv 2312.14890 | Text benchmark of 9 algorithmic tasks across complexity classes (P, NP-complete, NP-hard) with 10 difficulty levels and monthly refreshed instances | Exact, algorithmically graded optimization problems in text | Classical abstract problems (e.g. graph/scheduling); no 3D geometry, projections or connectivity-under-shape constraints |
| **Minecraft-builder LLM benchmark** — arXiv 2407.12734; **MineBench** ([site](https://minebench.ai/)) | Text-to-voxel construction: place blocks at coordinates; MineBench ranks free-form builds by blind human pairwise votes | Voxel coordinates as text; spatial construction | Builder tasks score matching or human preference; Shadow Twins uses exact verification against a certified optimum, no judges |
| **Orthographic/projection VLM benchmarks** — e.g. Spatial-DISE (arXiv 2510.13394), 3ViewSense (arXiv 2603.07751), 11Plus-Bench (arXiv 2508.20068) | Image-based questions on projections, views, block counting and mental rotation | Orthographic projections of 3D shapes | Perception/recognition questions with discrete answers; no editing, no optimization, no text-only geometry |

## Tentative distinction (to be substantiated)

The combination we have not yet found in one benchmark:

1. constrained **inverse design** (edit a given object) rather than recognition or free construction;
2. an **exact invariant** (three binary silhouettes) that interacts with the objective, measured
   per instance by the shadow-rejection rate and shadow traps;
3. an **internal topological objective** (empty-space connectivity between marked ports);
4. **exhaustively certified optima** with objective partial credit and an independent verifier;
5. **compact text-only** input (≤ 800 tokens under a frozen tokenizer panel).

Each ingredient exists elsewhere (Shadow Art: shadow-constrained voxel volumes; NPHardEval:
exact graded optimization in text; builder benchmarks: voxel coordinates in text). Before
presenting Shadow Twins as a research contribution, extend the search to: voxel/lattice
counterfactual reasoning benchmarks, CAD/engineering-drawing reconstruction from three views
(classical "three-view" problems), maze/grid path benchmarks for LLMs (text mazes), ARC-style
grid transformation tasks, and discrete tomography (reconstruction from projections), which is the
closest mathematical relative of the silhouette constraint.

## Limitations of this assessment

* Search breadth: a handful of targeted queries plus the three references named in the spec.
* Recent preprints (2025–2026) move quickly; results may be superseded.
* No author was contacted; descriptions come from public project pages and abstracts.
