# Phase 6 dev evaluation (DEV ONLY; LOCO; one Windows machine; machine transfer untested)

Frozen: `benchmarks\results\tier2-dev-b`; derived predictions: `benchmarks\results\phase6-dev-mains`. 422 valid (point, tier) time rows, 109 configurations.

## 1. Candidate selection (pre-registered: lowest pooled LOCO median log error subject to within-one >= 95% and same-bucket not below F)

| tier | candidate | n | log_err_med | log_err_p90 | err_med | err_p90 | bias | same | same_n | within_one |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | F (stored, old profile) | 211 | 0.59 | 1.40 | 53% | 239% | 1.07 | 75% | 159 | 100% |
| 0 | F | 211 | 0.65 | 1.34 | 53% | 164% | 0.77 | 72% | 151 | 100% |
| 0 | D | 211 | 0.73 | 1.67 | 55% | 308% | 0.93 | 75% | 158 | 100% |
| 0 | D+m | 211 | 0.36 | 1.43 | 33% | 194% | 0.98 | 73% | 154 | 100% |
| 1 | F (stored, old profile) | 211 | 0.58 | 1.33 | 53% | 224% | 1.07 | 75% | 158 | 100% |
| 1 | F | 211 | 0.64 | 1.29 | 52% | 146% | 0.79 | 73% | 153 | 100% |
| 1 | D | 211 | 0.33 | 0.82 | 32% | 76% | 1.01 | 86% | 182 | 100% |
| 1 | D+m | 211 | 0.25 | 0.92 | 25% | 89% | 1.01 | 86% | 181 | 100% |


Target (a) met at BOTH tiers: D: yes, D+m: yes. Selected (one candidate for the stack): **D+m**.

## 2.1 Tier 0 time per operation: BEFORE (frozen F, band 0.25x-4x)

| op | n | configs | err_med | err_p90 | bias | same | within_one | coverage | width |
|---|---|---|---|---|---|---|---|---|---|
| astype | 37 | 17 | 68% | 102% | 1.20 | 65% | 100% | 92% | 3.75 |
| drop_duplicates | 38 | 17 | 51% | 80% | 0.53 | 63% | 100% | 89% | 3.75 |
| groupby | 31 | 18 | 82% | 331% | 1.82 | 74% | 100% | 71% | 3.75 |
| merge | 24 | 19 | 27% | 68% | 0.76 | 88% | 100% | 100% | 3.75 |
| numpy.sort | 3 | 3 | 8% | 8% | 1.08 | 100% | 100% | 100% | 3.90 |
| operator.matmul | 19 | 6 | 18% | 152% | 0.91 | 84% | 100% | 100% | 4.80 |
| pandas.concat | 16 | 9 | 35% | 87% | 0.70 | 62% | 100% | 81% | 3.75 |
| pandas.read_csv | 17 | 10 | 72% | 178% | 0.32 | 59% | 100% | 94% | 3.75 |
| sort_values | 26 | 10 | 48% | 94% | 0.70 | 77% | 100% | 100% | 3.75 |
| ALL | 211 | 109 | 53% | 164% | 0.77 | 72% | 100% | 91% | 3.85 |


AFTER (selected D+m, LOCO conformal ranges)

| op | n | configs | err_med | err_p90 | bias | same | within_one | coverage | width |
|---|---|---|---|---|---|---|---|---|---|
| astype | 37 | 17 | 67% | 226% | 0.92 | 70% | 100% | 95% | 4.91 |
| drop_duplicates | 38 | 17 | 26% | 171% | 0.98 | 82% | 100% | 95% | 2.46 |
| groupby | 31 | 18 | 86% | 158% | 0.96 | 48% | 100% | 94% | 10.63 |
| merge | 24 | 19 | 39% | 82% | 1.03 | 83% | 100% | 92% | 2.23 |
| numpy.sort | 3 | 3 | 2% | 3% | 1.01 | 100% | 100% | 100% | 7.43 |
| operator.matmul | 19 | 6 | 10% | 18% | 0.99 | 95% | 100% | 100% | 7.43 |
| pandas.concat | 16 | 9 | 28% | 81% | 0.98 | 62% | 100% | 75% | 4.59 |
| pandas.read_csv | 17 | 10 | 20% | 770% | 0.96 | 76% | 100% | 82% | 1.27 |
| sort_values | 26 | 10 | 49% | 372% | 1.02 | 69% | 100% | 77% | 1.88 |
| ALL | 211 | 109 | 33% | 194% | 0.98 | 73% | 100% | 90% | 4.57 |


Range kind per operation: astype: per-operation, drop_duplicates: per-operation, groupby: per-operation, merge: per-operation, numpy.sort: generic, operator.matmul: generic, pandas.concat: per-operation, pandas.read_csv: per-operation, sort_values: per-operation

## 2.2 Tier 1 time per operation: BEFORE (frozen F, band 0.25x-4x)

| op | n | configs | err_med | err_p90 | bias | same | within_one | coverage | width |
|---|---|---|---|---|---|---|---|---|---|
| astype | 37 | 17 | 68% | 102% | 1.20 | 65% | 100% | 92% | 3.75 |
| drop_duplicates | 38 | 17 | 48% | 79% | 0.61 | 68% | 100% | 89% | 3.75 |
| groupby | 31 | 18 | 85% | 223% | 1.62 | 74% | 100% | 77% | 3.75 |
| merge | 24 | 19 | 27% | 68% | 0.76 | 88% | 100% | 100% | 3.75 |
| numpy.sort | 3 | 3 | 8% | 8% | 1.08 | 100% | 100% | 100% | 3.90 |
| operator.matmul | 19 | 6 | 18% | 152% | 0.91 | 84% | 100% | 100% | 4.80 |
| pandas.concat | 16 | 9 | 35% | 87% | 0.70 | 62% | 100% | 81% | 3.75 |
| pandas.read_csv | 17 | 10 | 72% | 178% | 0.32 | 59% | 100% | 94% | 3.75 |
| sort_values | 26 | 10 | 48% | 94% | 0.70 | 77% | 100% | 100% | 3.75 |
| ALL | 211 | 109 | 52% | 146% | 0.79 | 73% | 100% | 91% | 3.85 |


AFTER (selected D+m, LOCO conformal ranges)

| op | n | configs | err_med | err_p90 | bias | same | within_one | coverage | width |
|---|---|---|---|---|---|---|---|---|---|
| astype | 37 | 17 | 32% | 51% | 0.98 | 89% | 100% | 95% | 1.48 |
| drop_duplicates | 38 | 17 | 25% | 58% | 1.01 | 95% | 100% | 95% | 2.39 |
| groupby | 31 | 18 | 26% | 199% | 1.05 | 77% | 100% | 87% | 1.55 |
| merge | 24 | 19 | 24% | 64% | 1.02 | 88% | 100% | 92% | 1.62 |
| numpy.sort | 3 | 3 | 2% | 3% | 1.01 | 100% | 100% | 100% | 2.17 |
| operator.matmul | 19 | 6 | 10% | 18% | 0.99 | 95% | 100% | 100% | 2.17 |
| pandas.concat | 16 | 9 | 38% | 86% | 1.02 | 69% | 100% | 75% | 6.21 |
| pandas.read_csv | 17 | 10 | 12% | 37% | 1.00 | 100% | 100% | 82% | 0.89 |
| sort_values | 26 | 10 | 49% | 372% | 1.02 | 69% | 100% | 77% | 1.88 |
| ALL | 211 | 109 | 25% | 89% | 1.01 | 86% | 100% | 89% | 2.10 |


Range kind per operation: astype: per-operation, drop_duplicates: per-operation, groupby: per-operation, merge: per-operation, numpy.sort: generic, operator.matmul: generic, pandas.concat: per-operation, pandas.read_csv: per-operation, sort_values: per-operation

## 3. Tier 1 coverage by size bucket and by configuration

| size_bucket | coverage | n |
|---|---|---|
| 64-256 MiB | 89% | 53 |
| <64 MiB | 83% | 18 |
| >=256 MiB | 90% | 140 |


| op | size_bucket | coverage | n |
|---|---|---|---|
| astype | 64-256 MiB | 100% | 8 |
| astype | >=256 MiB | 93% | 29 |
| drop_duplicates | 64-256 MiB | 92% | 12 |
| drop_duplicates | <64 MiB | 100% | 1 |
| drop_duplicates | >=256 MiB | 96% | 25 |
| groupby | 64-256 MiB | 83% | 6 |
| groupby | >=256 MiB | 88% | 25 |
| merge | 64-256 MiB | 100% | 5 |
| merge | >=256 MiB | 89% | 19 |
| numpy.sort | 64-256 MiB | 100% | 3 |
| operator.matmul | 64-256 MiB | 100% | 10 |
| operator.matmul | >=256 MiB | 100% | 9 |
| pandas.concat | 64-256 MiB | 0% | 2 |
| pandas.concat | >=256 MiB | 86% | 14 |
| pandas.read_csv | <64 MiB | 82% | 17 |
| sort_values | 64-256 MiB | 71% | 7 |
| sort_values | >=256 MiB | 79% | 19 |


Configurations with every point outside the range: 11 of 109: v3/astype/int_to_category_card0p04, drop_duplicates/subset_s0_lowcard, groupby/cat_key_zipf_sum, v4/groupby/two_keys_card6000, merge/inner_overlap10, merge/outer_overlap50_realistic, v4/concat/two_category_heavy, read_csv/realistic_nulls, v3/read_csv/long_distinct_strings, v3/sort_values/int_datetime_lowcard, v3/sort_values/two_str_keys

## 4. What the derivation explained: bias of F and D (median expected/actual) and the fitted residual (multiplier applied to D, fitted on all configurations)

| tier | op | configs | D_bias | F_bias | residual_all |
|---|---|---|---|---|---|
| 0 | astype | 17 | 1.08 | 1.20 | 0.92 |
| 0 | drop_duplicates | 17 | 0.46 | 0.53 | 2.20 |
| 0 | groupby | 18 | 3.17 | 1.82 | 0.32 |
| 0 | merge | 19 | 0.36 | 0.76 | 2.80 |
| 0 | numpy.sort | 3 | 1.00 | 1.08 | 1.00 |
| 0 | operator.matmul | 6 | 1.00 | 0.91 | 1.00 |
| 0 | pandas.concat | 9 | 0.86 | 0.70 | 1.17 |
| 0 | pandas.read_csv | 10 | 1.08 | 0.32 | 0.92 |
| 0 | sort_values | 10 | 0.59 | 0.70 | 1.70 |
| 1 | astype | 17 | 0.80 | 1.20 | 1.25 |
| 1 | drop_duplicates | 17 | 1.44 | 0.61 | 0.70 |
| 1 | groupby | 18 | 1.29 | 1.62 | 0.78 |
| 1 | merge | 19 | 0.70 | 0.76 | 1.43 |
| 1 | numpy.sort | 3 | 1.00 | 1.08 | 1.00 |
| 1 | operator.matmul | 6 | 1.00 | 0.91 | 1.00 |
| 1 | pandas.concat | 9 | 1.18 | 0.70 | 0.85 |
| 1 | pandas.read_csv | 10 | 0.99 | 0.32 | 1.01 |
| 1 | sort_values | 10 | 0.59 | 0.70 | 1.70 |


## 5. Learned residual model (gradient-boosted trees on top of the selected candidate, LOCO)

Tier 0: pooled median log error 0.364 -> 0.307 (+15.6%; needs >= 10%), p90 1.430 -> 1.042, same bucket 154 -> 166 points, within one 211 -> 211: meets the conditions.

Tier 1: pooled median log error 0.251 -> 0.233 (+7.2%; needs >= 10%), p90 0.924 -> 0.671, same bucket 181 -> 185 points, within one 211 -> 211: does NOT meet the conditions.

**Learned residual NOT included** (must meet the conditions at both tiers).

## 6. Tier 2 time ranges (accepted time fits; expected unchanged)

BEFORE

| op | n | configs | coverage | above_high | width |
|---|---|---|---|---|---|
| astype | 36 | 17 | 78% | 0% | 1.33 |
| drop_duplicates | 29 | 15 | 79% | 14% | 9.57 |
| groupby | 14 | 10 | 50% | 43% | 1.33 |
| merge | 20 | 17 | 90% | 5% | 77.59 |
| numpy.sort | 3 | 3 | 100% | 0% | 1.14 |
| operator.matmul | 6 | 5 | 50% | 50% | 1.85 |
| pandas.concat | 5 | 4 | 80% | 0% | 27.41 |
| pandas.read_csv | 15 | 8 | 100% | 0% | 7.28 |
| sort_values | 20 | 10 | 85% | 15% | 12.09 |
| ALL | 148 | 89 | 80% | 11% | 16.21 |


AFTER (LOCO conformal on normalised scores)

| op | n | configs | coverage | above_high | width |
|---|---|---|---|---|---|
| astype | 36 | 17 | 92% | 0% | 11.07 |
| drop_duplicates | 29 | 15 | 93% | 0% | 2741 |
| groupby | 14 | 10 | 93% | 7% | 35.95 |
| merge | 20 | 17 | 95% | 0% | 97.30 |
| numpy.sort | 3 | 3 | 100% | 0% | 5.75 |
| operator.matmul | 6 | 5 | 67% | 33% | 57.31 |
| pandas.concat | 5 | 4 | 100% | 0% | 476576 |
| pandas.read_csv | 15 | 8 | 93% | 0% | 1.92 |
| sort_values | 20 | 10 | 95% | 5% | 2554 |
| ALL | 148 | 89 | 93% | 3% | 17005 |


Range kind: astype: per-operation, drop_duplicates: per-operation, groupby: per-operation, merge: per-operation, numpy.sort: generic, operator.matmul: generic, pandas.concat: generic, pandas.read_csv: per-operation, sort_values: per-operation

## 7. RAM no-regression (policy B unchanged; stored F vs re-run D predictions)

(point, tier) rows whose RAM low / expected / high changed: **42**.

| op | tier | n | above_high_f | coverage_f | width_f | cfg_above_high_f | above_high_d | coverage_d | width_d | cfg_above_high_d |
|---|---|---|---|---|---|---|---|---|---|---|
| astype | 0 | 49 | 0% | 92% | 0.99 | 0 | 0% | 92% | 0.99 | 0 |
| astype | 1 | 49 | 0% | 100% | 0.93 | 0 | 0% | 100% | 0.93 | 0 |
| drop_duplicates | 0 | 41 | 0% | 100% | 1.06 | 0 | 0% | 100% | 1.06 | 0 |
| drop_duplicates | 1 | 41 | 0% | 95% | 0.78 | 0 | 0% | 95% | 0.78 | 0 |
| groupby | 0 | 41 | 0% | 98% | 1.47 | 0 | 0% | 98% | 1.47 | 0 |
| groupby | 1 | 41 | 0% | 98% | 2.18 | 0 | 0% | 98% | 2.18 | 0 |
| merge | 0 | 37 | 0% | 95% | 3.66 | 0 | 0% | 95% | 3.66 | 0 |
| merge | 1 | 37 | 0% | 97% | 5.13 | 0 | 0% | 97% | 5.23 | 0 |
| numpy.sort | 0 | 12 | 0% | 100% | 0.40 | 0 | 0% | 100% | 0.40 | 0 |
| numpy.sort | 1 | 12 | 0% | 100% | 0.40 | 0 | 0% | 100% | 0.40 | 0 |
| operator.matmul | 0 | 24 | 0% | 100% | 1.25 | 0 | 0% | 100% | 1.25 | 0 |
| operator.matmul | 1 | 24 | 0% | 100% | 1.25 | 0 | 0% | 100% | 1.25 | 0 |
| pandas.concat | 0 | 27 | 0% | 100% | 1.00 | 0 | 0% | 100% | 1.00 | 0 |
| pandas.concat | 1 | 27 | 0% | 100% | 1.00 | 0 | 0% | 100% | 0.85 | 0 |
| pandas.read_csv | 0 | 24 | 0% | 96% | 2.65 | 0 | 0% | 96% | 2.65 | 0 |
| pandas.read_csv | 1 | 24 | 0% | 100% | 3.04 | 0 | 0% | 100% | 3.04 | 0 |
| sort_values | 0 | 29 | 0% | 100% | 0.45 | 0 | 0% | 100% | 0.45 | 0 |
| sort_values | 1 | 29 | 0% | 100% | 0.45 | 0 | 0% | 100% | 0.45 | 0 |
| ALL | 0 | 284 | 0% | 97% | 1.50 | 0 | 0% | 97% | 1.50 | 0 |
| ALL | 1 | 284 | 0% | 99% | 1.78 | 0 | 0% | 99% | 1.77 | 0 |


## 8. Regressions (pre-registered (d)); decisions are in docs/PROGRESS.md

- Tier 0 astype: p90 rel_err 102% -> 226%
- Tier 0 drop_duplicates: p90 rel_err 80% -> 171%
- Tier 0 groupby: median rel_err 82% -> 86%
- Tier 0 groupby: same bucket 23.0 -> 15 points
- Tier 0 merge: median rel_err 27% -> 39%
- Tier 0 merge: p90 rel_err 68% -> 82%
- Tier 0 merge: same bucket 21.0 -> 20 points
- Tier 0 pandas.read_csv: p90 rel_err 178% -> 770%
- Tier 0 pandas.read_csv: coverage 94% -> 82%
- Tier 0 sort_values: p90 rel_err 94% -> 372%
- Tier 0 sort_values: same bucket 20.0 -> 18 points
- Tier 0 ALL: p90 rel_err 164% -> 194%
- Tier 1 pandas.concat: median rel_err 35% -> 38%
- Tier 1 pandas.read_csv: coverage 94% -> 82%
- Tier 1 sort_values: p90 rel_err 94% -> 372%
- Tier 1 sort_values: same bucket 20.0 -> 18 points
- RAM tier 1 merge: width 5.13 -> 5.23
