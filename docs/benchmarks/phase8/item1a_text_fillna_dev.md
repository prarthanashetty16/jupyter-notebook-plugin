# v4 item (1a) text fillna: DEV evaluation (multicell cells, prediction only)

v3 models `src/nexus:38d1ec5d9126ea43`; working tree `src/nexus:7a7a30363c7b9847`. Model highs (no item C factors yet). Measured cells with a prediction in both: 327.

| cells | points | configs | above high (points) | above high (configs) | median error | coverage | high/expected median | p90 |
|---|---|---|---|---|---|---|---|---|
| NEW: estimated by the tree, not by v3 | 22 | 11 | 6 (27.3%) | 3 (27.3%) | 5.6% | 54.5% | 1.33 | 4.46 |
| both, v3 prediction | 184 | 92 | 4 (2.2%) | 2 (2.2%) | 1.6% | 85.3% | 4.43 | 10.62 |
| both, tree prediction | 184 | 92 | 4 (2.2%) | 2 (2.2%) | 1.6% | 85.3% | 4.43 | 10.62 |
| both, changed by the item (tree) | 4 | 4 | 0 (0.0%) | 0 (0.0%) | 60.9% | 0.0% | 3.84 | 4.28 |

* Cells that lost their estimate: 0 []
* W(a) on cells both estimate: median 1.000 (bar 1.30); cells whose prediction changed: 4.
* W(b) on NEW cells: median 1.33 (bar 2.0), p90 4.46 (bar 4.0); 22 cells (< 30: INCONCLUSIVE).

NEW cells (template, actual / low / expected / high MiB):

* `v1|copy_fillna/mixed@1000000`: 88 / 99 / 99 / 115
* `v1|copy_fillna/mixed@2000000`: 176 / 198 / 198 / 231
* `v2|v2:load_fillna/text@1500000`: 287 / 247 / 319 / 1424
* `v2|v2:load_fillna/text@3000000`: 560 / 495 / 639 / 2848
* `v2|v2:text_fillna/text@1500000`: 41 / 46 / 46 / 46
* `v2|v2:text_fillna/text@3000000`: 81 / 92 / 92 / 92
* `v3|v3:load_fillna_text/mixed@1250000`: 252 / 248 / 311 / 1580
* `v3|v3:load_fillna_text/mixed@2500000`: 500 / 496 / 622 / 3160
* `v3|v3:load_fillna_text/narrow@1250000`: 183 / 143 / 186 / 685
* `v3|v3:load_fillna_text/narrow@2500000`: 324 / 286 / 371 / 1369
* `v3|v3:load_fillna_text/text@1250000`: 250 / 206 / 266 / 1187
* `v3|v3:load_fillna_text/text@2500000`: 471 / 412 / 532 / 2373
* `v3|v3:load_fillna_text/textwide@1250000`: 358 / 245 / 341 / 1294
* `v3|v3:load_fillna_text/textwide@2500000`: 659 / 490 / 686 / 2588
* `v3|v3:text_fillna_cols/mixed@1250000`: 62 / 62 / 62 / 82
* `v3|v3:text_fillna_cols/mixed@2500000`: 124 / 124 / 124 / 165
* `v3|v3:text_fillna_cols/narrow@1250000`: 46 / 44 / 44 / 44  **ABOVE HIGH**
* `v3|v3:text_fillna_cols/narrow@2500000`: 91 / 88 / 88 / 88  **ABOVE HIGH**
* `v3|v3:text_fillna_cols/text@1250000`: 74 / 73 / 73 / 73  **ABOVE HIGH**
* `v3|v3:text_fillna_cols/text@2500000`: 148 / 145 / 145 / 145  **ABOVE HIGH**
* `v3|v3:text_fillna_cols/textwide@1250000`: 94 / 92 / 92 / 92  **ABOVE HIGH**
* `v3|v3:text_fillna_cols/textwide@2500000`: 186 / 184 / 184 / 184  **ABOVE HIGH**
