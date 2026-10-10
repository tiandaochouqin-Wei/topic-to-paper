# topic-to-paper

A Claude Code skill that drives a research topic to a submission package through machine-checked gates. You say one sentence; Claude runs every script.

- **Research branch** P0–P8: venue selection → literature + innovation scan → preregistration (locked by sha256) → build audit (leakage, effective config, silent fallbacks) → experiments (traceability, seeds, ablation resolution, anomaly triage) → figures → writing (must-write checklist, family-specific shape) → review loop → submission package.
- **Survey branch** S0–S6: protocol, search log, screening sheet, codebook, PRISMA counts, claim-to-row traceability.
- Every gate is a script with a FAIL/WARN/PASS verdict. Rules were calibrated on 275 published papers (CVPR, NeurIPS, ICML, MICCAI, TPAMI, TIP, IJCV, Nature Communications/Medicine/BME/MI) and validated on real manuscripts (see `references/validation-*.md`).

## Install

Claude Code loads skills from either of two folders:

| Scope | Folder | When |
|---|---|---|
| Just you, every project | `~/.claude/skills/topic-to-paper/` | personal use |
| One repository, every collaborator | `<repo>/.claude/skills/topic-to-paper/` | commit it; teammates get it on clone |

```bash
# personal
git clone https://github.com/tiandaochouqin-Wei/topic-to-paper ~/.claude/skills/topic-to-paper
pip install -r ~/.claude/skills/topic-to-paper/requirements.txt
python ~/.claude/skills/topic-to-paper/scripts/t2p.py doctor
```

`doctor` checks the three required Python packages and that every script answers `--help` under a GBK console (the default on Chinese Windows). `python -m pytest tests -q` runs the regression suite: two fixture projects on which every offline gate must PASS, plus one mutation per failure mode each gate exists for (see `tests/README.md`). Optional: `pdflatex` (table compile check), a local PDF corpus for the zero-token literature index (see below).

## Use

In Claude Code, inside the project folder, say one of:

- `用 topic-to-paper 开始 <方向>` / `start a paper on <topic>` → research branch from P0
- `帮我做一篇 <主题> 的综述` / `write a survey on <topic>` → survey branch from S0
- `这是我的稿子 <path>，帮我过一遍` → runs the writing gates on an existing LaTeX/PDF/markdown draft
- `resume <project>` → continues from the first failed gate in `research-state.yaml` (`t2p.py check` writes every gate's status back into it; `t2p.py status` reads it)

A project can start anywhere: `t2p.py init --entry have_draft` (or `have_results`, `have_reviews`) marks the gates whose inputs do not exist yet as N/A instead of PENDING, so "check my draft" is not sent back to literature search.

Claude replies with a status board (one line per gate) and a short "what I need from you" list. The four things it will stop for: credentials (data portals, compute allocations, journal systems), a choice between materially different readings of the request, changing a locked preregistration, and authorship/submit.

## What it checks (short list)

| Gate | What would otherwise go wrong |
|---|---|
| G1b innovation source | claim not traceable to a recurring gap, a stated assumption in a prior paper, or a transferred method's failure point; direction has no "no-go" exit |
| G2 preregistration | metric/denominator/window changed after seeing results; no failure branch; no pre-stated signs |
| G3 build audit | target-domain labels leak into training; an `args.beta=0.1` that never took effect; a missing input directory silently disabling a modality |
| G4 results | numbers not traceable to eval files; stale evals; mixed hardware in one table; ablation cells inside seed noise read as effects; anomalies patched instead of recorded |
| G5 figures | dpi measured on screen not at print width; legibility never inspected |
| G6 manuscript | DOI strings that resolve to other papers; orphan figures; acronyms never expanded; "outperforms all" without a scope; table numbers that drift from result files; venue hard limits |
| G6b/G6c writing | the sentence a section must contain is missing or in the wrong section; a CS-shaped draft sent to a Nature-family journal (Related Work, Conclusion, contribution list, equations in the main text) |
| G7 review loop | a major comment never closed in a re-review; G6 not re-run after edits |
| G8 submission docs | title page / cover letter numbers that no longer match the body; a blind copy with the author's name in it |

Generators, not just checks: SOTA/multi-dataset/ablation/seed tables with best/second-best marks and automatic provenance registration; main/ablation/seed figures from the result tables; qualitative result grids with insets; a remote experiment bundle (pre-flight env check, smoke run, full matrix, collect) for the "Claude writes the scripts, you run them on the server" workflow.

## Optional: local literature index

`scripts/lit_scout.py build <papers_root> <index.sqlite>` builds an FTS5 index from a folder of PDFs plus `metadata/index.csv` (venue, year, title, local_path) so saturation counts and candidate scouting cost zero tokens. Without it, P1 uses CrossRef / arXiv / OpenAlex / Semantic Scholar directly; the skill works, it just makes more API calls. Set your own contact email in `scripts/transfer_scan.py` (`UA`) — OpenAlex and CrossRef give polite-pool rate limits to requests that identify themselves.

## Layout

```
SKILL.md                 execution instructions for Claude (not a user manual): routing table, three rules, one index row per stage
scripts/                 24 gate/generator scripts, all argparse, all `--help`
tests/                   pytest regression suite + two fixture projects (research_min, survey_min)
templates/               research-state.yaml, prereg.md, protocol.md, codebook.md, skeleton-{cs_conf,cs_journal,nature}.md, …
references/              gates.md (why each gate exists), phases/P0–P8.md + S0–S6.md (per-stage detail, read on entering a stage), lessons.md, routing.md, venue-profiles.md, venue-norms.csv, acronym-norms.csv, validation-*.md
```

## Limits (stated honestly)

Fully autonomous publication is not possible: data credentials, compute, pivot decisions after a null result, and the submit button are the user's. The second and third of the three innovation tests (structural correspondence, failure point) are written by Claude after reading a paper, not computed. Shape checks verify form, not whether the claim is right. P4 from the first run to the main table has been validated on a one-epoch smoke run and on a finished 22-run project, not yet end-to-end on a fresh project; the Slurm branch of the bundle is untested.

## License

MIT. Calibration statistics in `references/` are aggregates; no paper text is redistributed.
