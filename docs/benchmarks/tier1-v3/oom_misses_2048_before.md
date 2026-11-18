# OOM false negatives at 2048 MB (development data)

| tier | rule | point_id | actual_MiB | input_MiB | predicted_MiB | low_MiB | planner_footprint_MiB | planner_flags |
|---|---|---|---|---|---|---|---|---|
| 1 | high | v4/astype/float_to_str_nulls|n=10000000 | 665 | 1689 | 0.00 | 0.00 | 939 | False |
| 1 | expected | v4/astype/float_to_str_nulls|n=10000000 | 665 | 1689 | 0.00 | 0.00 | 939 | False |
