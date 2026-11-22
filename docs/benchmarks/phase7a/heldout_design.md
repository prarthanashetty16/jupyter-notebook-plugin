# Phase 7a: held-out designs for freeze v3 (designed, NOT run)

Mode **B**: val-v5 has not been run and stays sealed and unread. It is the held-out Linux run for `models-frozen-v3`.
test-v2 stays sealed and is not part of the v3 check. Every held-out set below runs **once**, on the frozen v3 stack
(freeze guard first), on mains power, through an entry point that logs the access. Results are reported as they come
out, and a set that has been read becomes dev.

## (a) Multi-statement group v2 (`benchmarks/multicell/cases_v2.py`, split `split_v2.json`)

| property | v2 |
|---|---|
| templates | 15 (below), 43 configurations (template x shape), 2 sizes each |
| held-out | per template, the configuration with the largest `sha256("phase7-multicell-v2:" + key)`: **15 configurations, 30 cells** |
| dev | the other 28 configurations (56 cells): Phase 7b development data |
| sizes | 1.5M and 3M rows (v1: 1M, 2M) |
| seeds | df 11, df2 12, right 13 (v1: 1, 2, 3); generator values shared with v1: none |
| shapes | `num`, `mixed`, `wide` (v1 generators, new seeds); new: `text` (2 pandas-3 `str` columns with 5% missing, a float column with NaN), `lists` / `lists_long` (a list column, Poisson mean 4 / 12) |
| leak protection | as v1: `split.load(version=2)` checks the digest and that the file matches the configurations; held-out console output is id / status / time only; results in `benchmarks/results/multicell_v2/heldout/`; read only by `python -m benchmarks.multicell.run evaluate --version 2 --heldout --reason "..."`; every run / evaluate access is appended to `docs/benchmarks/phase7-heldout-access-log.md`; the runner requires the freeze guard and the held-out profile check (`benchmarks/heldout_env.py`) |
| when created | `split_v2.json` is written AFTER the Phase 7 pre-registration commit and BEFORE any v3 model change |

Templates (what each one tests):

| template | source | shapes |
|---|---|---|
| loads_usecols_dtype | `a = read_csv(P1, usecols=['k','v','f0'])`; `b = read_csv(P2, dtype={'v': 'float32'})` | num, wide, mixed |
| load_nrows_merge | `a = read_csv(P1, nrows=HALF)`; `m = a.merge(right, on='k')` (frame created in the cell) | num, wide, mixed |
| load_fillna | `a = read_csv(P1)`; `b = a.fillna(0)` (created frame; text: incompatible fill value) | num, wide, text |
| concat_reads_groupby | `parts = concat([read_csv(P1), read_csv(P2)])`; `g = parts.groupby('k')['v'].sum()` | num, wide, mixed |
| loads_tsv_na | `a = read_csv(T1, sep='\t', na_values=['NA'])`; `b = read_csv(P2, header=0)` | num, wide, mixed |
| set_index_copy | `s = df.set_index('k')`; `c = s.copy()` | num, mixed, text |
| value_counts_dedup | `vc = df['k'].value_counts()`; `d = df.drop_duplicates(subset=['k'])` | num, mixed, text |
| explode_groupby | `e = df['l'].explode()`; `g = df.groupby('k')['v'].sum()` | lists, lists_long |
| apply_forms | `a = df['v'].apply(np.sqrt)`; `b = df['f0'].apply(lambda x: x * 2)` | num, wide, mixed |
| text_fillna | `z = df['s0'].fillna('missing')`; `y = df[['s0','s1']].fillna('z')` | text, mixed |
| chain_copy | `r = df.sort_values('v').drop_duplicates(subset=['k']).copy()` | num, mixed, wide |
| copy_astype | `x = df.copy()`; `c = x['k'].astype('category')` (created frame) | num, mixed, text |
| merge_del_groupby | `m = df.merge(right, on='k')`; `del m`; `g = df.groupby('k')['v'].mean()` | num, mixed, wide |
| sort_then_groupby | `s = df.sort_values('v')`; `g = s.groupby('k')['v'].sum()` (created frame) | num, mixed, wide |
| concat_then_dedup | `c = concat([df, df2])`; `d = c.drop_duplicates(subset=['k'])` (created frame) | num, mixed, text |

Operations that v3 leaves uncovered stay in these templates on purpose: they test the "no estimate" / UNKNOWN path. The group
is fixed now, before the coverage decision of Phase 7b, so it cannot be shaped around what v3 covers.

## (b) Suggestion held-out

No suggestion rule is in the v3 scope. The suggestion engine re-estimates with the v3 models, but its rules and filter
thresholds (`suggestions/engine.py`, frozen) do not change. **No new suggestion held-out group is created.** If Phase 7b
changes a rule after all, a fresh suggestion split (new version, new seeds) and its own pre-registration amendment must be
committed before that change.

## (c) val-v5 (Mode B): as is

47 configurations (split version 6, seeds >= 501, sizes up to 30M rows, np.sort to 400M, matmul to 16000). The Linux VM
needs >= 32 GB RAM. Runbook: `docs/benchmarks/val-v5-linux-runbook.md`, with the tag replaced by `models-frozen-v3`.
Nothing about it is read or changed in Phase 7. The v3 read_csv model depends on the CPUs available to the process
(the parallel reader uses min(cpu_count, 6, available CPUs) threads), so the VM's `cpu_count` and affinity are recorded in
every row (they already are: `cpu_count`) and must be > 1. A VM with 1 vCPU is not a valid val-v5 machine for v3.

## (d) Fresh real-notebook set (Phase 8b): what to collect and how it runs

**What you collect (I download nothing; tell me where the folder is once it is complete):**

1. **>= 30 notebooks by at least 10 different authors, none by you**, and none of the three Phase 8a notebooks or their
   forks. Sources: public Kaggle notebooks (licence shown on the page; Apache 2.0 is Kaggle's default) or GitHub
   repositories with a LICENSE file that permits copying and running (MIT, BSD, Apache 2.0, CC-BY).
2. **pandas-heavy:** chosen by what the notebook says it does (EDA, cleaning, feature engineering, joins, aggregation).
   You choose them by title / description; no tool of mine opens them before the pre-registration commit.
3. **Datasets:** each notebook's input data, licence checked (CC0, CC-BY, ODbL, or the competition's terms permit local
   use), **<= 1 GiB on disk per notebook**, so that a cell's peak can stay under the watchdog cap (70% of free RAM; this laptop
   has ~5 GiB free, which is what stopped Phase 8a). Larger datasets: only for a Linux-VM run, listed separately.
4. A `manifest.csv` next to them: `notebook, author, source_url, notebook_licence, dataset, dataset_url, dataset_licence,
   dataset_bytes, needs_gpu, needs_internet`. Notebooks that need a GPU, internet, Colab paths or credentials are excluded up
   front (Phase 8a lost one notebook to `google.colab`).
5. Keep everything OUTSIDE the repository (for example `C:\dev\nexus-data\phase8b\`). Notebooks, data and outputs are never
   committed. The records hold cell hashes, operation names, shapes and numbers only, as in Phase 8a.

**How Phase 8b runs, once:**

1. `docs/benchmarks/phase8b-preregistration.md` is written and committed **before any notebook is opened**. It covers the
   sample as collected (from the manifest only), the criteria of the Phase 7 pre-registration section 4, the environment
   (pandas 3.1.1, numpy 2.5.5, no pyarrow unless you decide otherwise before the commit), the watchdog cap and the exclusions.
2. `git checkout models-frozen-v3 && python -m benchmarks.frozen check` (0 problems), mains power, the reference machine profile.
3. Static coverage first (`python -m benchmarks.realworld.coverage <folder> --out docs/benchmarks/phase8b/coverage`):
   the coverage criterion is computed for v3 AND for `models-frozen-v2` on the same cells (static analysis, no execution).
4. Then `python -m benchmarks.realworld.run_notebook <copy> --out benchmarks/results/realworld/phase8b/<name> --tier 1` per
   notebook (no `--dev`), and `python -m benchmarks.realworld.evaluate_real ...` once.
5. The result is reported as it comes out; nothing is tuned on it; the set is dev afterwards.
