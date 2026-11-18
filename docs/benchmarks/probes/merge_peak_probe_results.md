# Merge peak probe (results)

OS peak above baseline, MiB (median of repeats; `censored` = below the setup peak). `saving` = 1 - selected/full; `merge-only` = 1 - preselected/full. `dropped share` = bytes of the dropped columns (both frames) / bytes of both input frames.

| mix | rows | right rows | inputs MiB | dropped share | full | selected | preselected | saving | merge-only saving |
|---|---|---|---|---|---|---|---|---|---|
| float6 | 500,000 | 1,000 | 31 | 75% | 20 | 21 | 20 | -0% | 0% |
| float6 | 1,000,000 | 1,000 | 61 | 75% | 32 | 33 | 32 | -0% | 0% |
| float6 | 2,000,000 | 1,000 | 122 | 75% | 62 | 56 | 56 | 9% | 9% |
| float6 | 500,000 | 500,000 | 46 | 75% | 36 | 36 | 36 | -0% | 0% |
| float6 | 1,000,000 | 500,000 | 76 | 75% | 56 | 56 | 56 | -0% | 0% |
| float6 | 2,000,000 | 500,000 | 137 | 75% | 80 | 80 | 80 | -0% | -0% |
| float2 | 500,000 | 1,000 | 15 | 50% | 20 | 21 | 20 | -0% | 0% |
| float2 | 1,000,000 | 1,000 | 31 | 50% | 32 | 33 | 32 | -0% | 0% |
| float2 | 2,000,000 | 1,000 | 61 | 50% | 62 | 56 | 56 | 9% | 9% |
| float2 | 500,000 | 500,000 | 31 | 62% | 36 | 36 | 36 | -0% | -0% |
| float2 | 1,000,000 | 500,000 | 46 | 58% | 56 | 56 | 56 | -0% | 0% |
| float2 | 2,000,000 | 500,000 | 76 | 55% | 80 | 80 | 80 | -0% | 0% |
| int6 | 500,000 | 1,000 | 31 | 75% | 20 | 21 | 20 | -0% | 0% |
| int6 | 1,000,000 | 1,000 | 61 | 75% | 32 | 33 | 32 | -0% | 0% |
| int6 | 2,000,000 | 1,000 | 122 | 75% | 62 | 56 | 56 | 9% | 9% |
| int6 | 500,000 | 500,000 | 46 | 75% | 36 | 36 | 36 | -0% | -0% |
| int6 | 1,000,000 | 500,000 | 76 | 75% | 56 | 56 | 56 | -0% | -0% |
| int6 | 2,000,000 | 500,000 | 137 | 75% | 80 | 80 | 80 | -0% | -0% |
| mixed | 500,000 | 1,000 | 79 | 90% | 20 | 20 | 20 | -0% | -3% |
| mixed | 1,000,000 | 1,000 | 158 | 90% | 32 | 32 | 32 | -1% | -1% |
| mixed | 2,000,000 | 1,000 | 317 | 90% | censored | censored | 56 | n/a | n/a |
| mixed | 500,000 | 500,000 | 94 | 88% | 36 | 36 | 36 | -0% | -2% |
| mixed | 1,000,000 | 500,000 | 174 | 89% | 56 | 56 | 56 | -0% | -0% |
| mixed | 2,000,000 | 500,000 | 332 | 90% | 80 | 80 | 80 | 0% | -0% |

## tracemalloc stage peaks (MiB above the stage start); sites live near the peak

* float6 500,000/1,000 full: select 0, merge 28, merge_result 11, final_column 0; near-peak 24. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200; 3.8 MiB @ merge.py:3050 <- merge.py:2200
* float6 500,000/1,000 selected: select 0, merge 28, merge_result 0, final_column 0; near-peak 28. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200; 3.8 MiB @ merge.py:3051 <- merge.py:2200
* float6 500,000/1,000 preselected: select 0, merge 28, merge_result 0, final_column 0; near-peak 24. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200; 3.8 MiB @ merge.py:3050 <- merge.py:2200
* float6 1,000,000/1,000 full: select 0, merge 56, merge_result 23, final_column 0; near-peak 56. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* float6 1,000,000/1,000 selected: select 0, merge 56, merge_result 0, final_column 0; near-peak 56. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* float6 1,000,000/1,000 preselected: select 0, merge 56, merge_result 0, final_column 0; near-peak 56. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* float6 2,000,000/1,000 full: select 0, merge 80, merge_result 46, final_column 0; near-peak 80. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* float6 2,000,000/1,000 selected: select 0, merge 80, merge_result 0, final_column 0; near-peak 80. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* float6 2,000,000/1,000 preselected: select 0, merge 80, merge_result 0, final_column 0; near-peak 80. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* float6 500,000/500,000 full: select 0, merge 36, merge_result 11, final_column 0; near-peak 36. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3042 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200
* float6 500,000/500,000 selected: select 0, merge 36, merge_result 0, final_column 0; near-peak 36. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3042 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200
* float6 500,000/500,000 preselected: select 0, merge 36, merge_result 0, final_column 0; near-peak 36. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3042 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200
* float6 1,000,000/500,000 full: select 0, merge 64, merge_result 23, final_column 0; near-peak 64. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* float6 1,000,000/500,000 selected: select 0, merge 64, merge_result 0, final_column 0; near-peak 64. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* float6 1,000,000/500,000 preselected: select 0, merge 64, merge_result 0, final_column 0; near-peak 64. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* float6 2,000,000/500,000 full: select 0, merge 88, merge_result 46, final_column 0; near-peak 88. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* float6 2,000,000/500,000 selected: select 0, merge 88, merge_result 0, final_column 0; near-peak 88. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* float6 2,000,000/500,000 preselected: select 0, merge 88, merge_result 0, final_column 0; near-peak 88. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* float2 500,000/1,000 full: select 0, merge 28, merge_result 11, final_column 0; near-peak 24. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200; 3.8 MiB @ merge.py:3050 <- merge.py:2200
* float2 500,000/1,000 selected: select 0, merge 28, merge_result 0, final_column 0; near-peak 24. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200; 3.8 MiB @ merge.py:3050 <- merge.py:2200
* float2 500,000/1,000 preselected: select 0, merge 28, merge_result 0, final_column 0; near-peak 28. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200; 3.8 MiB @ merge.py:3051 <- merge.py:2200
* float2 1,000,000/1,000 full: select 0, merge 56, merge_result 23, final_column 0; near-peak 56. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* float2 1,000,000/1,000 selected: select 0, merge 56, merge_result 0, final_column 0; near-peak 56. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* float2 1,000,000/1,000 preselected: select 0, merge 56, merge_result 0, final_column 0; near-peak 56. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* float2 2,000,000/1,000 full: select 0, merge 80, merge_result 46, final_column 0; near-peak 80. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* float2 2,000,000/1,000 selected: select 0, merge 80, merge_result 0, final_column 0; near-peak 80. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* float2 2,000,000/1,000 preselected: select 0, merge 80, merge_result 0, final_column 0; near-peak 80. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* float2 500,000/500,000 full: select 0, merge 36, merge_result 11, final_column 0; near-peak 36. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3042 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200
* float2 500,000/500,000 selected: select 0, merge 36, merge_result 0, final_column 0; near-peak 36. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3042 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200
* float2 500,000/500,000 preselected: select 0, merge 36, merge_result 0, final_column 0; near-peak 36. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3042 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200
* float2 1,000,000/500,000 full: select 0, merge 64, merge_result 23, final_column 0; near-peak 64. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* float2 1,000,000/500,000 selected: select 0, merge 64, merge_result 0, final_column 0; near-peak 64. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* float2 1,000,000/500,000 preselected: select 0, merge 64, merge_result 0, final_column 0; near-peak 64. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* float2 2,000,000/500,000 full: select 0, merge 88, merge_result 46, final_column 0; near-peak 88. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* float2 2,000,000/500,000 selected: select 0, merge 88, merge_result 0, final_column 0; near-peak 88. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* float2 2,000,000/500,000 preselected: select 0, merge 88, merge_result 0, final_column 0; near-peak 88. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* int6 500,000/1,000 full: select 0, merge 28, merge_result 11, final_column 0; near-peak 28. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200; 3.8 MiB @ merge.py:3051 <- merge.py:2200
* int6 500,000/1,000 selected: select 0, merge 28, merge_result 0, final_column 0; near-peak 24. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200; 3.8 MiB @ merge.py:3050 <- merge.py:2200
* int6 500,000/1,000 preselected: select 0, merge 28, merge_result 0, final_column 0; near-peak 28. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200; 3.8 MiB @ merge.py:3051 <- merge.py:2200
* int6 1,000,000/1,000 full: select 0, merge 56, merge_result 23, final_column 0; near-peak 56. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* int6 1,000,000/1,000 selected: select 0, merge 56, merge_result 0, final_column 0; near-peak 56. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* int6 1,000,000/1,000 preselected: select 0, merge 56, merge_result 0, final_column 0; near-peak 56. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* int6 2,000,000/1,000 full: select 0, merge 80, merge_result 46, final_column 0; near-peak 80. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* int6 2,000,000/1,000 selected: select 0, merge 80, merge_result 0, final_column 0; near-peak 80. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* int6 2,000,000/1,000 preselected: select 0, merge 80, merge_result 0, final_column 0; near-peak 80. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* int6 500,000/500,000 full: select 0, merge 36, merge_result 11, final_column 0; near-peak 36. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3042 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200
* int6 500,000/500,000 selected: select 0, merge 36, merge_result 0, final_column 0; near-peak 32. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3042 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200
* int6 500,000/500,000 preselected: select 0, merge 36, merge_result 0, final_column 0; near-peak 36. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3042 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200
* int6 1,000,000/500,000 full: select 0, merge 64, merge_result 23, final_column 0; near-peak 64. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* int6 1,000,000/500,000 selected: select 0, merge 64, merge_result 0, final_column 0; near-peak 64. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* int6 1,000,000/500,000 preselected: select 0, merge 64, merge_result 0, final_column 0; near-peak 64. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* int6 2,000,000/500,000 full: select 0, merge 88, merge_result 46, final_column 0; near-peak 88. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* int6 2,000,000/500,000 selected: select 0, merge 88, merge_result 0, final_column 0; near-peak 88. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* int6 2,000,000/500,000 preselected: select 0, merge 88, merge_result 0, final_column 0; near-peak 88. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* mixed 500,000/1,000 full: select 0, merge 28, merge_result 11, final_column 0; near-peak 28. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200; 3.8 MiB @ merge.py:3051 <- merge.py:2200
* mixed 500,000/1,000 selected: select 0, merge 28, merge_result 0, final_column 0; near-peak 28. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200; 3.8 MiB @ merge.py:3051 <- merge.py:2200
* mixed 500,000/1,000 preselected: select 0, merge 28, merge_result 0, final_column 0; near-peak 28. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200; 3.8 MiB @ merge.py:3051 <- merge.py:2200
* mixed 1,000,000/1,000 full: select 0, merge 56, merge_result 23, final_column 0; near-peak 56. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* mixed 1,000,000/1,000 selected: select 0, merge 56, merge_result 0, final_column 0; near-peak 56. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* mixed 1,000,000/1,000 preselected: select 0, merge 56, merge_result 0, final_column 0; near-peak 56. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* mixed 2,000,000/1,000 full: select 0, merge 80, merge_result 46, final_column 0; near-peak 80. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* mixed 2,000,000/1,000 selected: select 0, merge 80, merge_result 0, final_column 0; near-peak 80. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* mixed 2,000,000/1,000 preselected: select 0, merge 80, merge_result 0, final_column 0; near-peak 80. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* mixed 500,000/500,000 full: select 0, merge 36, merge_result 11, final_column 0; near-peak 36. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3042 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200
* mixed 500,000/500,000 selected: select 0, merge 36, merge_result 0, final_column 0; near-peak 36. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3042 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200
* mixed 500,000/500,000 preselected: select 0, merge 36, merge_result 0, final_column 0; near-peak 36. Sites: 16.1 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3042 <- merge.py:2200; 3.8 MiB @ merge.py:3047 <- merge.py:2200
* mixed 1,000,000/500,000 full: select 0, merge 64, merge_result 23, final_column 0; near-peak 64. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* mixed 1,000,000/500,000 selected: select 0, merge 64, merge_result 0, final_column 0; near-peak 64. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3051 <- merge.py:2200
* mixed 1,000,000/500,000 preselected: select 0, merge 64, merge_result 0, final_column 0; near-peak 56. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 7.6 MiB @ merge.py:3047 <- merge.py:2200; 7.6 MiB @ merge.py:3042 <- merge.py:2200
* mixed 2,000,000/500,000 full: select 0, merge 88, merge_result 46, final_column 0; near-peak 88. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* mixed 2,000,000/500,000 selected: select 0, merge 88, merge_result 0, final_column 0; near-peak 88. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
* mixed 2,000,000/500,000 preselected: select 0, merge 88, merge_result 0, final_column 0; near-peak 88. Sites: 32.3 MiB @ merge.py:3018 <- merge.py:2200; 15.3 MiB @ merge.py:3047 <- merge.py:2200; 15.3 MiB @ merge.py:3051 <- merge.py:2200
