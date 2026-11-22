# Phase 6c probes (isolated, OS peak, inputs from disk, mains power, pandas 3.1.1 / numpy 2.5.5)

Every change of Phase 6c was derived from pandas source and then checked here at >= 200 MiB where the
case allows it. Raw outputs are next to each script (`*.out`). A derivation the probe contradicted was not
adopted as derived (pre-registration section 4); where the pandas source then explained the difference, the
corrected derivation was probed again (run 2), and that is stated per row.

| item | probe | result | adopted |
|---|---|---|---|
| cell model: retained outputs + current peak | `p_multistatement.py` | 7 cells (two / three loads, load then merge, sort-del-dedup, chain, expression statements, copy then fillna): measured cell peak = retained-before + own peak of the operation **exactly (1.00)** on every cell; the v1 "max of the operations" under-predicts the retaining cells (335 vs 360, 335 vs 500, 92 vs 160 MiB) | yes (`nexus/cellpeak.py`) |
| `copy()` consolidated frame | `p_copy_fillna.py` | 244 MiB = moved bytes, **1.00** | yes |
| `copy()` fragmented frame | run 1: 427 vs 244 (1.75, contradicted); pandas source: `BlockManager.copy(deep=True)` then `_consolidate_inplace` stacks each numpy dtype group again; run 2: 427 vs 427, **1.00** | yes (run-2 derivation) |
| `copy(deep=False)`, `fillna` without NaN, `fillna` dict | censored (below the ~63 MiB setup peak); consistent with 0 / 0 / 46 MiB | yes (not resolvable here) |
| `fillna(scalar)` float block | run 1: 183 vs 137 (1.33, contradicted); source: `Block.fillna` -> `Block.where` keeps 4 bool arrays alive (mask, ~mask, ~cond, ~icond); run 2: 183 vs 183, **1.00** | yes (run-2 derivation) |
| `fillna` on a pandas-3 `str` (extension) column | 84 vs 34 MiB (2.45x); the `ExtensionArray.fillna` path was not derived | **no: refused** (no estimate) |
| `read_csv(sep='\t')`, `header=None` | 617 MiB, identical to the default read of the same data (the v1 formula's known 0.84 band) | **yes**: one-character `sep` / `delimiter` and `header` 0 / None reach Tier 1 |
| `read_csv(dtype=...)` | float32 columns: 467 vs 689 derived (0.68): the value-size derivation is contradicted (the saving is 3x larger) | **no**: Tier 0 kept, display "unsupported arguments" |
| `read_csv(usecols=...)` | 108 vs 482 derived (0.22): the 1.6 x file-bytes term is NOT whole-file tokenizer memory; it scales with the converted columns | **no** (and a finding about the v1 model's structure: a Phase 7 input) |
| `read_csv(nrows=...)` | 91 vs 245 derived (0.37): no chunk-concatenation term for a truncated read | **no** |
