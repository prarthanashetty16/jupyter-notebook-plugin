# Phase 6c multi-statement held-out part: outcome and follow-up (information only)

Held-out report: `multicell_heldout.md` (regenerated 2026-11-22 from the STORED results after a formatting
fix: the `actual` column is MiB and `v1_bias` is a ratio; before, both were wrongly printed as percentages;
no figure changed). Every access is in `../phase6c-heldout-access-log.md`. **These 22 cells are dev data from
now on.** Nothing here changes a model, a threshold or a frozen file; everything below is a proposal.

Method for 3a-3c: a prediction-only Tier 1 re-run of the 22 cells on the cached inputs, one spawned process per
cell (`probes/p_heldout_followup.py`, output `probes/p_heldout_followup.jsonl`). No measurement. **All 22 cells
reproduce the stored `new` and `v1` estimates exactly**, so the per-operation terms below are the ones behind the
stored figures. A retained-frame size comes from arithmetic: every load template reads an all-numeric frame
(int64 / float64; `num` 64 B/row, `wide` 96 B/row; float32 where `dtype` says so). An "implied" measured
peak of the last load is the stored cell actual minus the true retained sizes of the frames loaded earlier.

## 1. Outcome, as it came out

| | new (cellpeak) | v1 (combine) |
|---|---|---|
| above_high | **0 of 22 cells, 0 of 11 configurations: both bars MET** | 0 / 0 |
| bias (median predicted / actual) | 1.17 | 1.00 |
| median error | 17.2% | 6.0% |
| coverage | 63.6% (36.4% below `low`) | 86.4% |
| width | 3.04 | 6.05 |

* With 0 events in 22 cells, the one-sided 95% upper bound on the true above-high rate is **12.7%**
  (Clopper-Pearson; 15.4% two-sided). For 0 of 11 configurations it is 23.8%. Meeting the bar shows the rate
  is not large. It does not show the rate is at or below 3%.
* **The median-error ranking flipped.** On dev the new model had 12.6% vs 17.8% for v1. On held-out it has
  17.2% vs 6.0%. The new model's gain is the halved width (3.04 vs 6.05), not the point error.
* Coverage 63.6% on both dev and held-out. Every miss is below `low` (over-prediction with a narrow range).
* 6 cells have operations without an estimate: load_then_merge x2 (merge on a frame made in the cell),
  concat_loads x2 (concat of calls), copy_fillna/mixed x2 (`fillna(0)` on pandas-3 `str` columns, refused).
  On dev, copy_fillna had none (its dev shapes have no text columns).

## 3a. Risk class of the six cells with uncovered operations (frozen engine, simulated headroom)

| cell | actual / high | 64-256 MiB | 512 MiB | 1 GiB | 2 GiB | 4 GiB | >= 8 GiB |
|---|---|---|---|---|---|---|---|
| load_then_merge/wide@1M | 0.14 | HIGH_RISK | WARN | WARN | WARN | UNKNOWN | UNKNOWN |
| load_then_merge/wide@2M | 0.14 | HIGH_RISK | HIGH_RISK | WARN | WARN | WARN | UNKNOWN |
| concat_loads/wide@1M | 0.17 | HIGH_RISK | HIGH_RISK | WARN | WARN | UNKNOWN | UNKNOWN |
| concat_loads/wide@2M | 0.17 | HIGH_RISK | HIGH_RISK | HIGH_RISK | WARN | WARN | UNKNOWN |
| copy_fillna/mixed@1M | 0.85 | HIGH_RISK (64), UNKNOWN (128, 256) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| copy_fillna/mixed@2M | 0.85 | HIGH_RISK (64, 128), UNKNOWN (256) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

**None of the six is ever OK.** `classify` turns an otherwise-OK cell with an uncovered operation into UNKNOWN.
At no headroom is a cell UNKNOWN while its actual peak exceeds the headroom: UNKNOWN only occurs when
`high <= 0.85 x headroom`, and actual <= high for all six. copy_fillna's high (actual / high 0.85) holds only
because the `copy` term (91.6 MiB retained) covers the refused `fillna(0)`.
*Proposal:* none needed for safety. The wording could name the uncovered operation ("no estimate for
`df.fillna(0)`").

## 3b. Is the 1.1-1.25 bias the read_csv Tier 1 over-prediction?

| cell | plain-load retained: predicted vs true (MiB) | last plain load: predicted peak / implied measured | cell bias |
|---|---|---|---|
| loads2/num@1M | 61.0 vs 61.0 | 286.8 / 235.6 = **1.22** | 1.17 |
| loads2/num@2M | 122.1 vs 122.1 | 573.6 / 469.5 = **1.22** | 1.18 |
| loads3_tsv/wide@1M | 91.6 vs 91.6 | 493.7 / 394.5 = **1.25** | 2.02 (3c) |
| loads3_tsv/wide@2M | 183.1 vs 183.1 | 987.4 / 786.5 = **1.26** | 2.02 (3c) |
| load_then_merge/wide@1M | 91.6 vs 91.6 | 493.7 / 394.5 = **1.25** | 1.25 |
| load_then_merge/wide@2M | 183.1 vs 183.1 | 987.4 / 786.2 = **1.26** | 1.26 |
| concat_loads/wide@1M | 91.6 vs 91.6 | 493.7 / 394.5 = **1.25** | 1.20 |
| concat_loads/wide@2M | 183.1 vs 183.1 | 987.4 / 786.9 = **1.25** | 1.21 |

* **Retained sizes are exact** (the `models._output` read_csv term; within 0.1%). The cell model's bookkeeping is
  not the source.
* **The bias of the load templates is the read_csv Tier 1 peak term**: 1.22x (num) and 1.25x (wide) per load. That
  is the known 0.84 band of the v1 formula (the Phase 6c probe: 617 measured vs 735 derived). The cell bias is
  lower than 1.25 where an exact retained term is added (loads2, concat_loads).
* Cross-check: the implied peak of a plain 1M-row wide load is 394.5 MiB in three independent templates
  (loads3_tsv, load_then_merge, concat_loads), and 786.2-786.9 MiB at 2M. Two assumptions hold up here: the
  peak sits at the last load, and the uncovered merge / concat stayed below it.
* **The read_csv term does NOT explain all of the 1.1-1.17 bias.** Templates without a load are also biased:
  copy_fillna 1.17, chain 1.14, rebinding 1.11, astype_groupby 1.11 (deletes and expressions 0.99). Those come
  from other terms: Tier 0 `copy` on text columns, the chain's Tier 0 `sort_values`, astype / groupby Tier 1.
  Not analysed here.

*Proposal (Phase 7, a new derivation, not a fit to these numbers):* the read_csv transient term. The Phase 6c
probe already showed that the 1.6 x file-bytes term scales with the converted columns rather than the whole file.
Re-deriving it would address both this 0.80-0.82 measured / predicted ratio and the usecols case below. It must be
checked on fresh data. These 22 cells are dev now and cannot validate it.

## 3c. load_dtype_nrows and loads3_tsv: share of the error from the dtype / usecols / nrows arguments

**loads3_tsv** (`b = read_csv(T1, sep='\t', usecols=['k', 'v'])` falls back to Tier 0; a and c are Tier 1):

| size | predicted / actual | error | b retained: predicted vs true | if b were exact | **usecols share** | rest (read_csv Tier 1 band on c) |
|---|---|---|---|---|---|---|
| 1M | 1012 / 501 | 510 MiB | 240.7 vs 15.3 | 601 (bias 1.20) | **80.6%** | 19.4% |
| 2M | 2023 / 1000 | 1023 MiB | 481.4 vs 30.5 | 1201 (bias 1.20) | **80.4%** | 19.6% |

The predicted peak sits at statement b: retained a plus b's Tier 0 peak (920 MiB at 1M). The measured peak sits
at c: 91.6 + 15.3 + 394.5 = 501.4 vs 501.3 measured. "If b were exact" puts b's true retained 2 columns in and
caps its peak at the actual.

**load_dtype_nrows** (both loads fall back to Tier 0 because of the arguments):

| size | predicted / actual | error | Tier 1 on the same files, arguments ignored | Tier 0 vs Tier 1 share | arguments ignored at Tier 1 | of which the Tier 1 band (assumption) |
|---|---|---|---|---|---|---|
| 1M | 1161 / 334 | 827 MiB | 585 (bias 1.75) | **69.6%** | **30.4%** | ~7.6% |
| 2M | 2322 / 625 | 1697 MiB | 1171 (bias 1.87) | **67.8%** | **32.2%** | ~6.7% |

All of the error sits in the two argument-carrying operations: a's retained term is 240.7 vs 83.9 MiB true at
1M (float32 columns), and b's peak is 920 vs an implied 250.5 MiB (half the rows). About 70% comes from the
Tier 0 fallback that the arguments trigger: Tier 0 already over-predicts a plain read of this file 2.3x
(920 vs 394.5). About 23-25% comes from the argument content (whole file vs half the rows / narrower dtypes). The
last ~7% is the read_csv Tier 1 band. That split assumes the 1.25x band also applies to the truncated read, an
assumption the probe's nrows row (0.37) argues against. Treat it as approximate.

*Proposals (not implemented; need a fresh derivation, a probe and a new freeze):*
1. `usecols` (80% of loads3_tsv's error): the retained term is just arithmetic (only the kept columns). The
   transient term needs the per-column re-derivation above (the probe: 0.22 vs the v1 structure).
2. `nrows`: scale the rows term by `min(nrows, rows)`. This needs the chunk term the probe found missing (0.37).
3. `dtype`: the retained term from the target itemsizes is exact here (83.9 MiB). The transient saving was 3x the
   derived one (0.68), so the transient needs its own derivation.
4. Until then, the Tier 0 fallback could keep the Tier 1 retained term for these arguments when it is plain
   arithmetic (usecols / dtype / nrows on a file whose header and sample are already read). This would only
   change `models/_output.py` and `models/read_csv.py`, so it needs a new freeze.
