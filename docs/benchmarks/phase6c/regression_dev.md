# Phase 6c regression check on all existing dev data (pre-registration B)

Before: `benchmarks\results\phase6-dev-mains` (models-frozen-v1); after: `benchmarks\results\phase6c-dev` (Phase 6c). 646 (point, tier) rows in both; only in before: 0, only in after: 0.

* rows whose RAM low / expected / high changed: **16** (astype, drop_duplicates, groupby, pandas.concat)
* rows whose calibrated expected time changed: **51** (astype, drop_duplicates, groupby, pandas.concat)

| op | tier | above_high before | above_high after | ram_cov before | ram_cov after | ram_width before | ram_width after | t_err_med before | t_err_med after | same_n before | same_n after | within_one_n before | within_one_n after | t_cov before | t_cov after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 0 | 0 | 0 | 0.918 | 0.918 | 0.995 | 0.995 | 0.635 | 0.635 | 26 | 26 | 37 | 37 | 0.973 | 0.973 |
| astype | 1 | 0 | 0 | 1 | 1 | 0.926 | 0.926 | 0.262 | 0.262 | 33 | 33 | 37 | 37 | 1 | 1 |
| drop_duplicates | 0 | 0 | 0 | 1 | 1 | 1.06 | 1.06 | 0.243 | 0.243 | 31 | 31 | 38 | 38 | 1 | 1 |
| drop_duplicates | 1 | 0 | 0 | 0.951 | 0.951 | 0.775 | 0.788 | 0.216 | 0.212 | 36 | 36 | 38 | 38 | 1 | 0.947 |
| groupby | 0 | 0 | 0 | 0.976 | 0.976 | 1.47 | 1.47 | 0.784 | 0.784 | 17 | 17 | 31 | 31 | 1 | 1 |
| groupby | 1 | 0 | 0 | 0.976 | 0.976 | 2.18 | 2.18 | 0.239 | 0.239 | 25 | 25 | 31 | 31 | 0.968 | 0.968 |
| merge | 0 | 0 | 0 | 0.946 | 0.946 | 3.66 | 3.66 | 0.316 | 0.316 | 20 | 20 | 24 | 24 | 1 | 1 |
| merge | 1 | 0 | 0 | 0.973 | 0.973 | 5.23 | 5.23 | 0.236 | 0.236 | 21 | 21 | 24 | 24 | 1 | 1 |
| numpy.sort | 0 | 0 | 0 | 1 | 1 | 0.4 | 0.4 | 0.0088 | 0.0088 | 3 | 3 | 3 | 3 | 1 | 1 |
| numpy.sort | 1 | 0 | 0 | 1 | 1 | 0.4 | 0.4 | 0.0088 | 0.0088 | 3 | 3 | 3 | 3 | 1 | 1 |
| operator.matmul | 0 | 0 | 0 | 1 | 1 | 1.25 | 1.25 | 0.0894 | 0.0894 | 18 | 18 | 19 | 19 | 1 | 1 |
| operator.matmul | 1 | 0 | 0 | 1 | 1 | 1.25 | 1.25 | 0.0894 | 0.0894 | 18 | 18 | 19 | 19 | 1 | 1 |
| pandas.concat | 0 | 0 | 0 | 1 | 1 | 1 | 1 | 0.229 | 0.229 | 12 | 12 | 16 | 16 | 0.875 | 0.875 |
| pandas.concat | 1 | 0 | 0 | 1 | 1 | 0.847 | 0.869 | 0.298 | 0.272 | 11 | 11 | 16 | 16 | 0.875 | 0.875 |
| pandas.read_csv | 0 | 0 | 0 | 0.958 | 0.958 | 2.65 | 2.65 | 0.167 | 0.167 | 13 | 13 | 17 | 17 | 1 | 1 |
| pandas.read_csv | 1 | 0 | 0 | 1 | 1 | 3.04 | 3.04 | 0.116 | 0.116 | 17 | 17 | 17 | 17 | 1 | 1 |
| sort_values | 0 | 0 | 0 | 1 | 1 | 0.45 | 0.45 | 0.419 | 0.419 | 18 | 18 | 26 | 26 | 0.885 | 0.885 |
| sort_values | 1 | 0 | 0 | 1 | 1 | 0.45 | 0.45 | 0.419 | 0.419 | 18 | 18 | 26 | 26 | 0.885 | 0.885 |

## Regressions (pre-registered B)

- drop_duplicates tier 1: ram_width 0.7751 -> 0.788
- drop_duplicates tier 1: t_cov 1 -> 0.9474
- groupby tier 1: ram_width 2.177 -> 2.177
- pandas.concat tier 1: ram_width 0.8472 -> 0.8686

## Rows whose RAM changed

- drop_duplicates/mixed_dup50|n=10000000 tier 1: 1206 -> 1305 MiB expected, high 2115 -> 2115
- drop_duplicates/numeric_dup50|n=10000000 tier 1: 1152 -> 957 MiB expected, high 1658 -> 1658
- drop_duplicates/subset_s0_lowcard|n=10000000 tier 1: 27 -> 27 MiB expected, high 985 -> 985
- drop_duplicates/subset_i0_s0_lowcard|n=3000000 tier 1: 240 -> 240 MiB expected, high 288 -> 288
- drop_duplicates/subset_i0_s0_lowcard|n=10000000 tier 1: 801 -> 801 MiB expected, high 961 -> 961
- groupby/two_keys_mean_realistic|n=1000000 tier 1: 104 -> 104 MiB expected, high 150 -> 150
- concat/three_frames|n=10000000 tier 1: 885 -> 770 MiB expected, high 1426 -> 1426
- v3/drop_duplicates/null_heavy_full|n=10000000 tier 1: 1686 -> 1339 MiB expected, high 2115 -> 2115
- v3/drop_duplicates/high_survivor_subset_i0_d0|n=10000000 tier 1: 801 -> 801 MiB expected, high 961 -> 961
- v3/groupby/int_card20000_mean|n=1000000 tier 1: 28 -> 28 MiB expected, high 76 -> 76
- v3/concat/four_frames_light_nulls|n=10000000 tier 1: 885 -> 770 MiB expected, high 1426 -> 1426
- v3/concat/two_strings_long|n=10000000 tier 1: 656 -> 541 MiB expected, high 968 -> 968
- v4/astype/int_to_category_card15000|n=1000000 tier 1: 27 -> 27 MiB expected, high 56 -> 56
- v4/groupby/two_keys_card6000|n=1000000 tier 1: 108 -> 108 MiB expected, high 150 -> 150
- v4/drop_duplicates/null_subset_cat_date|n=3000000 tier 1: 209 -> 209 MiB expected, high 288 -> 288
- v4/drop_duplicates/null_subset_cat_date|n=10000000 tier 1: 690 -> 691 MiB expected, high 961 -> 961
