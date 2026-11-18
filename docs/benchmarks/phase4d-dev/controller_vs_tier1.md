# Phase 4d: the controller replayed on DEVELOPMENT data (every number is dev)

322 development points (dev + exposed-v1 + val-v3 + val-v4) with Tier 0 / 1 / 2 predictions; Tier 1 = Tier 1 low / expected with Tier 0's high (policy B). The real `Controller` runs on stored dry runs; see the docstring of `benchmarks/controller_eval.py`.


## Free RAM scenario: 2.5 GiB (the dev cap)

| op | points | variant | ram_n | ram_err_med | ram_cov | ram_above_high | ram_below_low | ram_width | time_n | time_err_med | time_within_one | time_same_bucket | time_cov | escalated | tier2_used | fail_closed | unsafe | overhead_med_s | overhead_frac_med |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 63 | tier1 | 49 | 1% | 100% | 0% | 0% | 93% | 37 | 65% | 100% | 65% | 97% |  |  |  |  |  |  |
| astype | 63 | controller | 49 | 1% | 100% | 0% | 0% | 93% | 37 | 65% | 100% | 65% | 97% | 0% | 0% | 0% | 0% |  |  |
| drop_duplicates | 46 | tier1 | 40 | 12% | 95% | 0% | 5% | 79% | 38 | 34% | 100% | 74% | 89% |  |  |  |  |  |  |
| drop_duplicates | 46 | controller | 40 | 12% | 95% | 0% | 5% | 79% | 38 | 34% | 100% | 74% | 89% | 7% | 0% | 0% | 2% | 6.47 | 0.35 |
| groupby | 51 | tier1 | 41 | 2% | 98% | 0% | 2% | 218% | 31 | 157% | 100% | 74% | 74% |  |  |  |  |  |  |
| groupby | 51 | controller | 41 | 2% | 98% | 0% | 2% | 218% | 31 | 157% | 100% | 74% | 74% | 0% | 0% | 0% | 8% |  |  |
| merge | 37 | tier1 | 37 | 8% | 97% | 0% | 3% | 513% | 24 | 38% | 100% | 83% | 100% |  |  |  |  |  |  |
| merge | 37 | controller | 37 | 8% | 97% | 0% | 3% | 513% | 24 | 20% | 100% | 92% | 96% | 49% | 46% | 0% | 0% | 2.74 | 4.67 |
| numpy.sort | 16 | tier1 | 12 | 0% | 100% | 0% | 0% | 40% | 3 | 21% | 100% | 100% | 100% |  |  |  |  |  |  |
| numpy.sort | 16 | controller | 12 | 0% | 100% | 0% | 0% | 40% | 3 | 21% | 100% | 100% | 100% | 0% | 0% | 0% | 0% |  |  |
| operator.matmul | 29 | tier1 | 24 | 3% | 100% | 0% | 0% | 125% | 19 | 9% | 100% | 89% | 100% |  |  |  |  |  |  |
| operator.matmul | 29 | controller | 24 | 3% | 100% | 0% | 0% | 125% | 19 | 9% | 100% | 89% | 100% | 3% | 0% | 0% | 0% | 2.25 | 1.27 |
| pandas.concat | 27 | tier1 | 27 | 8% | 100% | 0% | 0% | 100% | 16 | 31% | 100% | 69% | 81% |  |  |  |  |  |  |
| pandas.concat | 27 | controller | 27 | 8% | 100% | 0% | 0% | 100% | 16 | 31% | 100% | 69% | 81% | 19% | 0% | 0% | 0% | 6.34 | 5.4 |
| pandas.read_csv | 24 | tier1 | 24 | 22% | 100% | 0% | 0% | 304% | 17 | 68% | 100% | 59% | 100% |  |  |  |  |  |  |
| pandas.read_csv | 24 | controller | 24 | 22% | 100% | 0% | 0% | 304% | 17 | 44% | 100% | 71% | 100% | 54% | 33% | 25% | 0% | 1.89 | 3.79 |
| sort_values | 29 | tier1 | 29 | 1% | 100% | 0% | 0% | 45% | 26 | 40% | 100% | 85% | 96% |  |  |  |  |  |  |
| sort_values | 29 | controller | 29 | 1% | 100% | 0% | 0% | 45% | 26 | 40% | 100% | 85% | 96% | 14% | 0% | 0% | 0% | 5.88 | 0.662 |
| ALL | 322 | tier1 | 283 | 3% | 99% | 0% | 1% | 178% | 211 | 53% | 100% | 75% | 92% |  |  |  |  |  |  |
| ALL | 322 | controller | 283 | 3% | 99% | 0% | 1% | 178% | 211 | 44% | 100% | 77% | 91% | 14% | 8% | 2% | 2% | 2.72 | 4.08 |


Triggers that fired: {'a': 47, 'a,b': 4, 'b': 4}; fail-closed: 6; unsafe: 5; Tier 2 used: 25 of 322.


## Free RAM scenario: 8 GiB

| op | points | variant | ram_n | ram_err_med | ram_cov | ram_above_high | ram_below_low | ram_width | time_n | time_err_med | time_within_one | time_same_bucket | time_cov | escalated | tier2_used | fail_closed | unsafe | overhead_med_s | overhead_frac_med |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 63 | tier1 | 49 | 1% | 100% | 0% | 0% | 93% | 37 | 65% | 100% | 65% | 97% |  |  |  |  |  |  |
| astype | 63 | controller | 49 | 1% | 100% | 0% | 0% | 93% | 37 | 65% | 100% | 65% | 97% | 0% | 0% | 0% | 0% |  |  |
| drop_duplicates | 46 | tier1 | 40 | 12% | 95% | 0% | 5% | 79% | 38 | 34% | 100% | 74% | 89% |  |  |  |  |  |  |
| drop_duplicates | 46 | controller | 40 | 12% | 95% | 0% | 5% | 79% | 38 | 34% | 100% | 74% | 89% | 4% | 0% | 0% | 2% | 6.54 | 0.383 |
| groupby | 51 | tier1 | 41 | 2% | 98% | 0% | 2% | 218% | 31 | 157% | 100% | 74% | 74% |  |  |  |  |  |  |
| groupby | 51 | controller | 41 | 2% | 98% | 0% | 2% | 218% | 31 | 157% | 100% | 74% | 74% | 0% | 0% | 0% | 0% |  |  |
| merge | 37 | tier1 | 37 | 8% | 97% | 0% | 3% | 513% | 24 | 38% | 100% | 83% | 100% |  |  |  |  |  |  |
| merge | 37 | controller | 37 | 8% | 97% | 0% | 3% | 513% | 24 | 38% | 100% | 83% | 100% | 0% | 0% | 0% | 0% |  |  |
| numpy.sort | 16 | tier1 | 12 | 0% | 100% | 0% | 0% | 40% | 3 | 21% | 100% | 100% | 100% |  |  |  |  |  |  |
| numpy.sort | 16 | controller | 12 | 0% | 100% | 0% | 0% | 40% | 3 | 21% | 100% | 100% | 100% | 0% | 0% | 0% | 0% |  |  |
| operator.matmul | 29 | tier1 | 24 | 3% | 100% | 0% | 0% | 125% | 19 | 9% | 100% | 89% | 100% |  |  |  |  |  |  |
| operator.matmul | 29 | controller | 24 | 3% | 100% | 0% | 0% | 125% | 19 | 9% | 100% | 89% | 100% | 3% | 0% | 0% | 0% | 2.25 | 1.27 |
| pandas.concat | 27 | tier1 | 27 | 8% | 100% | 0% | 0% | 100% | 16 | 31% | 100% | 69% | 81% |  |  |  |  |  |  |
| pandas.concat | 27 | controller | 27 | 8% | 100% | 0% | 0% | 100% | 16 | 31% | 100% | 69% | 81% | 0% | 0% | 0% | 0% |  |  |
| pandas.read_csv | 24 | tier1 | 24 | 22% | 100% | 0% | 0% | 304% | 17 | 68% | 100% | 59% | 100% |  |  |  |  |  |  |
| pandas.read_csv | 24 | controller | 24 | 22% | 100% | 0% | 0% | 304% | 17 | 64% | 100% | 88% | 100% | 25% | 25% | 0% | 0% | 2.23 | 1.44 |
| sort_values | 29 | tier1 | 29 | 1% | 100% | 0% | 0% | 45% | 26 | 40% | 100% | 85% | 96% |  |  |  |  |  |  |
| sort_values | 29 | controller | 29 | 1% | 100% | 0% | 0% | 45% | 26 | 40% | 100% | 85% | 96% | 14% | 0% | 0% | 0% | 5.88 | 0.662 |
| ALL | 322 | tier1 | 283 | 3% | 99% | 0% | 1% | 178% | 211 | 53% | 100% | 75% | 92% |  |  |  |  |  |  |
| ALL | 322 | controller | 283 | 3% | 99% | 0% | 1% | 178% | 211 | 52% | 100% | 77% | 92% | 4% | 2% | 0% | 0% | 2.27 | 1.12 |


Triggers that fired: {'b': 8, 'a': 6}; fail-closed: 0; unsafe: 1; Tier 2 used: 6 of 322.


## Free RAM scenario: 32 GiB

| op | points | variant | ram_n | ram_err_med | ram_cov | ram_above_high | ram_below_low | ram_width | time_n | time_err_med | time_within_one | time_same_bucket | time_cov | escalated | tier2_used | fail_closed | unsafe | overhead_med_s | overhead_frac_med |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 63 | tier1 | 49 | 1% | 100% | 0% | 0% | 93% | 37 | 65% | 100% | 65% | 97% |  |  |  |  |  |  |
| astype | 63 | controller | 49 | 1% | 100% | 0% | 0% | 93% | 37 | 65% | 100% | 65% | 97% | 0% | 0% | 0% | 0% |  |  |
| drop_duplicates | 46 | tier1 | 40 | 12% | 95% | 0% | 5% | 79% | 38 | 34% | 100% | 74% | 89% |  |  |  |  |  |  |
| drop_duplicates | 46 | controller | 40 | 12% | 95% | 0% | 5% | 79% | 38 | 34% | 100% | 74% | 89% | 4% | 0% | 0% | 2% | 6.54 | 0.383 |
| groupby | 51 | tier1 | 41 | 2% | 98% | 0% | 2% | 218% | 31 | 157% | 100% | 74% | 74% |  |  |  |  |  |  |
| groupby | 51 | controller | 41 | 2% | 98% | 0% | 2% | 218% | 31 | 157% | 100% | 74% | 74% | 0% | 0% | 0% | 0% |  |  |
| merge | 37 | tier1 | 37 | 8% | 97% | 0% | 3% | 513% | 24 | 38% | 100% | 83% | 100% |  |  |  |  |  |  |
| merge | 37 | controller | 37 | 8% | 97% | 0% | 3% | 513% | 24 | 38% | 100% | 83% | 100% | 0% | 0% | 0% | 0% |  |  |
| numpy.sort | 16 | tier1 | 12 | 0% | 100% | 0% | 0% | 40% | 3 | 21% | 100% | 100% | 100% |  |  |  |  |  |  |
| numpy.sort | 16 | controller | 12 | 0% | 100% | 0% | 0% | 40% | 3 | 21% | 100% | 100% | 100% | 0% | 0% | 0% | 0% |  |  |
| operator.matmul | 29 | tier1 | 24 | 3% | 100% | 0% | 0% | 125% | 19 | 9% | 100% | 89% | 100% |  |  |  |  |  |  |
| operator.matmul | 29 | controller | 24 | 3% | 100% | 0% | 0% | 125% | 19 | 9% | 100% | 89% | 100% | 3% | 0% | 0% | 0% | 2.25 | 1.27 |
| pandas.concat | 27 | tier1 | 27 | 8% | 100% | 0% | 0% | 100% | 16 | 31% | 100% | 69% | 81% |  |  |  |  |  |  |
| pandas.concat | 27 | controller | 27 | 8% | 100% | 0% | 0% | 100% | 16 | 31% | 100% | 69% | 81% | 0% | 0% | 0% | 0% |  |  |
| pandas.read_csv | 24 | tier1 | 24 | 22% | 100% | 0% | 0% | 304% | 17 | 68% | 100% | 59% | 100% |  |  |  |  |  |  |
| pandas.read_csv | 24 | controller | 24 | 22% | 100% | 0% | 0% | 304% | 17 | 68% | 100% | 59% | 100% | 0% | 0% | 0% | 0% |  |  |
| sort_values | 29 | tier1 | 29 | 1% | 100% | 0% | 0% | 45% | 26 | 40% | 100% | 85% | 96% |  |  |  |  |  |  |
| sort_values | 29 | controller | 29 | 1% | 100% | 0% | 0% | 45% | 26 | 40% | 100% | 85% | 96% | 14% | 0% | 0% | 0% | 5.88 | 0.662 |
| ALL | 322 | tier1 | 283 | 3% | 99% | 0% | 1% | 178% | 211 | 53% | 100% | 75% | 92% |  |  |  |  |  |  |
| ALL | 322 | controller | 283 | 3% | 99% | 0% | 1% | 178% | 211 | 53% | 100% | 75% | 92% | 2% | 0% | 0% | 0% | 6.08 | 0.584 |


Triggers that fired: {'b': 8}; fail-closed: 0; unsafe: 1; Tier 2 used: 0 of 322.


## WHAT-IF (not the pre-registered rules): always escalate when safe, 32 GiB free

| op | points | variant | ram_n | ram_err_med | ram_cov | ram_above_high | ram_below_low | ram_width | time_n | time_err_med | time_within_one | time_same_bucket | time_cov | escalated | tier2_used | fail_closed | unsafe | overhead_med_s | overhead_frac_med |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 63 | tier1 | 49 | 1% | 100% | 0% | 0% | 93% | 37 | 65% | 100% | 65% | 97% |  |  |  |  |  |  |
| astype | 63 | controller | 49 | 1% | 100% | 0% | 0% | 133% | 37 | 21% | 100% | 84% | 78% | 100% | 78% | 0% | 0% | 1.8 | 8.7 |
| drop_duplicates | 46 | tier1 | 40 | 12% | 95% | 0% | 5% | 79% | 38 | 34% | 100% | 74% | 89% |  |  |  |  |  |  |
| drop_duplicates | 46 | controller | 40 | 12% | 95% | 0% | 5% | 79% | 38 | 34% | 100% | 74% | 89% | 89% | 4% | 0% | 11% | 2.32 | 3.39 |
| groupby | 51 | tier1 | 41 | 2% | 98% | 0% | 2% | 218% | 31 | 157% | 100% | 74% | 74% |  |  |  |  |  |  |
| groupby | 51 | controller | 41 | 2% | 98% | 0% | 2% | 218% | 31 | 55% | 100% | 77% | 74% | 80% | 31% | 0% | 20% | 2.15 | 19.7 |
| merge | 37 | tier1 | 37 | 8% | 97% | 0% | 3% | 513% | 24 | 38% | 100% | 83% | 100% |  |  |  |  |  |  |
| merge | 37 | controller | 37 | 8% | 97% | 0% | 3% | 543% | 24 | 18% | 100% | 92% | 92% | 100% | 70% | 0% | 0% | 2.41 | 9.13 |
| numpy.sort | 16 | tier1 | 12 | 0% | 100% | 0% | 0% | 40% | 3 | 21% | 100% | 100% | 100% |  |  |  |  |  |  |
| numpy.sort | 16 | controller | 12 | 0% | 100% | 0% | 0% | 40% | 3 | 21% | 100% | 100% | 100% | 100% | 0% | 0% | 0% | 1.76 | 31.8 |
| operator.matmul | 29 | tier1 | 24 | 3% | 100% | 0% | 0% | 125% | 19 | 9% | 100% | 89% | 100% |  |  |  |  |  |  |
| operator.matmul | 29 | controller | 24 | 3% | 100% | 0% | 0% | 125% | 19 | 9% | 100% | 89% | 100% | 100% | 0% | 0% | 0% | 1.86 | 7.57 |
| pandas.concat | 27 | tier1 | 27 | 8% | 100% | 0% | 0% | 100% | 16 | 31% | 100% | 69% | 81% |  |  |  |  |  |  |
| pandas.concat | 27 | controller | 27 | 8% | 100% | 0% | 0% | 100% | 16 | 31% | 100% | 69% | 81% | 100% | 0% | 0% | 0% | 2.55 | 15.2 |
| pandas.read_csv | 24 | tier1 | 24 | 22% | 100% | 0% | 0% | 304% | 17 | 68% | 100% | 59% | 100% |  |  |  |  |  |  |
| pandas.read_csv | 24 | controller | 24 | 22% | 100% | 0% | 0% | 304% | 17 | 5% | 100% | 100% | 100% | 100% | 75% | 0% | 0% | 1.9 | 3.6 |
| sort_values | 29 | tier1 | 29 | 1% | 100% | 0% | 0% | 45% | 26 | 40% | 100% | 85% | 96% |  |  |  |  |  |  |
| sort_values | 29 | controller | 29 | 1% | 100% | 0% | 0% | 45% | 26 | 40% | 100% | 85% | 96% | 100% | 3% | 0% | 0% | 2.54 | 2.03 |
| ALL | 322 | tier1 | 283 | 3% | 99% | 0% | 1% | 178% | 211 | 53% | 100% | 75% | 92% |  |  |  |  |  |  |
| ALL | 322 | controller | 283 | 3% | 99% | 0% | 1% | 189% | 211 | 28% | 100% | 83% | 88% | 95% | 35% | 0% | 5% | 2.03 | 8.51 |


Tier 2 used: 112 of 322.
