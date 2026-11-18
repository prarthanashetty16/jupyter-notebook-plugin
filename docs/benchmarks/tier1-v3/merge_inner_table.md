# Inner-join points in dev (valid RAM, Tier 1 used), sorted by output/left rows

Predictions of the 4b.2 models (the merge model is unchanged in 4b.3). Source: `benchmarks/results/dev-v5`, script `docs/benchmarks/val-v3-diagnosis/probes/pg1_merge_inner_table.py`.

| point | overlap | fan-out | right unique | true output rows | Tier 1 est. rows | est/true rows | M / n_left | M / (n_left+n_right) | actual MiB | Tier 1 expected MiB | fold (exp/actual) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v4/merge/inner_overlap20_fanout10  n=3000000 | 0.20 | 10 | False | 90,000 | 86,040 | 0.96 | 0.03 | 0.03 | 179.0 | 142.1 | 0.79 |
| v4/merge/inner_overlap20_fanout10  n=1000000 | 0.20 | 10 | False | 30,000 | 29,810 | 0.99 | 0.03 | 0.03 | 69.9 | 58.2 | 0.83 |
| merge/inner_overlap10  n=1000000 | 0.10 | 1 | True | 50,000 | 50,344 | 1.01 | 0.05 | 0.03 | 49.1 | 45.7 | 0.93 |
| merge/inner_overlap10  n=3000000 | 0.10 | 1 | True | 150,000 | 149,760 | 1.00 | 0.05 | 0.03 | 83.8 | 88.2 | 1.05 |
| v3/merge/inner_overlap25_fanout6  n=3000000 | 0.25 | 6 | False | 262,500 | 257,502 | 0.98 | 0.09 | 0.06 | 180.6 | 154.6 | 0.86 |
| v3/merge/inner_overlap25_fanout6  n=1000000 | 0.25 | 6 | False | 87,504 | 90,234 | 1.03 | 0.09 | 0.06 | 71.8 | 62.4 | 0.87 |
| v4/merge/inner_overlap35_fanout7  n=1000000 | 0.35 | 7 | False | 140,000 | 135,142 | 0.97 | 0.14 | 0.10 | 71.6 | 63.8 | 0.89 |
| v4/merge/inner_overlap35_fanout7  n=3000000 | 0.35 | 7 | False | 420,000 | 414,645 | 0.99 | 0.14 | 0.10 | 180.4 | 159.2 | 0.88 |
| merge/inner_fanout3  n=3000000 | 1.00 | 3 | False | 1,500,000 | 1,509,744 | 1.01 | 0.50 | 0.33 | 183.5 | 179.6 | 0.98 |
| merge/inner_1to1  n=1000000 | 1.00 | 1 | True | 500,000 | 500,856 | 1.00 | 0.50 | 0.33 | 55.1 | 55.8 | 1.01 |
| merge/inner_1to1  n=3000000 | 1.00 | 1 | True | 1,500,000 | 1,500,800 | 1.00 | 0.50 | 0.33 | 155.1 | 167.2 | 1.08 |
| merge/inner_fanout3  n=1000000 | 1.00 | 3 | False | 500,000 | 499,608 | 1.00 | 0.50 | 0.33 | 63.4 | 70.6 | 1.11 |
| v4/merge/inner_overlap55_fanout4p5  n=1000000 | 0.55 | 4.5 | False | 540,000 | 541,895 | 1.00 | 0.54 | 0.28 | 71.6 | 78.1 | 1.09 |
| v4/merge/inner_overlap55_fanout4p5  n=3000000 | 0.55 | 4.5 | False | 1,620,000 | 1,605,440 | 0.99 | 0.54 | 0.28 | 246.0 | 266.4 | 1.08 |
| v4/merge/inner_overlap95_fanout1p1  n=1000000 | 0.95 | 1.1 | False | 620,454 | 620,680 | 1.00 | 0.62 | 0.38 | 66.6 | 75.0 | 1.13 |
| v4/merge/inner_overlap95_fanout1p1  n=3000000 | 0.95 | 1.1 | False | 1,861,364 | 1,865,584 | 1.00 | 0.62 | 0.38 | 197.9 | 207.8 | 1.05 |
| v3/merge/inner_bigright_fanout8  n=1000000 | 0.45 | 8 | False | 900,000 | 904,592 | 1.01 | 0.90 | 0.30 | 94.2 | 100.8 | 1.07 |
| v3/merge/inner_bigright_fanout8  n=3000000 | 0.45 | 8 | False | 2,700,000 | 2,722,304 | 1.01 | 0.90 | 0.30 | 289.5 | 334.9 | 1.16 |
| merge/inner_manymany  n=1000000 | 1.00 | 3 | False | 999,650 | 1,005,432 | 1.01 | 1.00 | 0.67 | 104.1 | 112.0 | 1.08 |
| merge/inner_manymany  n=3000000 | 1.00 | 3 | False | 3,000,078 | 2,993,328 | 1.00 | 1.00 | 0.67 | 309.8 | 333.4 | 1.08 |
