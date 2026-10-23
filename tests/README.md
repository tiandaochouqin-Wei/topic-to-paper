# tests/ — regression suite for the gates

Run from the skill root (any OS; the suite forces UTF-8 for child processes and also checks that every script survives a GBK console):

```bash
python -m pytest tests -q
```

Needs `pytest` plus the packages in `requirements.txt`. No network: `G1`/`refs` (DOI resolution) is not exercised.

## What is covered

| File | Covers |
|---|---|
| `test_health.py` | `t2p.py doctor` is clean; every script answers `--help` under `PYTHONIOENCODING=gbk`; every script carries the UTF-8 stdout header |
| `test_t2p.py` | `run()`/`verdict()` report a crashed gate as `CRASH`, never `PASS`; full board on both fixtures is green; a crashing gate shows as `[CRASH] G4` and counts in the exit code |
| `test_research_gates.py` | G1b, G2, G3, G4, G5, G6 (floats/acronyms/numbers/limits), G6b, G6c, G7, G8: one `*_pass` test on the untouched fixture, then one mutation per failure mode the gate exists for |
| `test_instrument_gate.py` | G3b instrument calibration (uncovered loader, waiver, missing/stale/out-of-band output, vacuous broken control, contract mismatch, dump, train_loop reference) plus `stochastic_keys`, narrowed audit set, empty `reproductions`, self-certified triage |
| `test_algorithm.py` | pseudocode blocks: `make_algorithm.py` skeleton (algpseudocode / algorithmic / algorithm2e dialects, depth cap) and the seven checks (packages, caption/label/ref, source anchor, symbols, values vs the reference run, shape, result numbers), the `tex_to_md` mirror, G6 floats, readability/numbers blindness, G6c norms, the G6b item, `calibrate` on three tiny PDFs |
| `test_survey_gates.py` | G-S2 protocol, G-S3 coding, G-S5 claims, and the `coding/audit_summary.py --verify` round trip |
| `test_architecture.py` | `make_architecture.py` on a two-branch toy model (+ torchvision resnet18): trace depth 1/2/3 (stages in forward order, glue ops visible or collapsed with depth, ×n repeat collapsing, params total, edge labels only where the shape changes, `--stages`, `--dump-activations`), render with both engines (vector PDF, `--hide` re-routing, `--merge`, `--images`, `--show-params`, tikz escaping and compile failure, figures.csv row, G5 print font), `check` (code unchanged / comment-only edit / changed channel or kernel / model no longer loads, hand-added label in the .tex, params mismatch, stale spec, stage names vs Method section, input resolution vs the reference run), and the G5 line of `t2p.py check` |

## Fixtures

- `fixtures/research_min/` — a complete research-branch project (cs_journal family): 11 runs with `args.json`/`log.json`/`eval.json`, result tables whose every cell is registered in `paper/numbers.csv`, a manuscript that mirrors every sentence the gates look for, review log, submission package. `t2p.py check` on a copy prints PASS for G0 and G1b–G8 (G1 is SKIP without `--net`).
- `fixtures/survey_min/` — a complete survey-branch project: locked protocol, codebook, screening sheet, coded table, PRISMA counts, kappa, prior surveys, claims with evidence keys, and a summary table that `coding/audit_summary.py --verify` re-derives.

`conftest.py` copies a fixture to a temp dir per test, re-locks the `prereg.md` / `protocol.md` sha256 (text-mode, as the gate scripts hash it) and bumps `eval.json` mtimes, so the suite does not depend on checkout order or line endings. Mutations use `edit(path, old, new)`, which asserts that `old` is present — a stale mutation cannot pass by accident.

## Adding a gate or a rule

1. Make the untouched fixture satisfy the new rule (edit the fixture, not the test).
2. Add one mutation test that violates only the new rule and assert the gate's own `[FAIL]` wording.
3. If a new script is added, nothing else is needed: `test_health.py` globs `scripts/*.py`.
