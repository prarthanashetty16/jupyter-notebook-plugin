# v4 item (1d) copy receivers (cumulative with 1a, 1b): DEV evaluation (multicell cells, prediction only)

v3 models `src/nexus:38d1ec5d9126ea43`; working tree `content:b811b601a5d5260e`. Model highs (no item C factors yet). Measured cells with a prediction in both: 327.

| cells | points | configs | above high (points) | above high (configs) | median error | coverage | high/expected median | p90 |
|---|---|---|---|---|---|---|---|---|
| NEW: estimated by the tree, not by v3 | 52 | 26 | 16 (30.8%) | 8 (30.8%) | 2.3% | 59.6% | 1.33 | 4.39 |
| both, v3 prediction | 184 | 92 | 4 (2.2%) | 2 (2.2%) | 1.6% | 85.3% | 4.43 | 10.62 |
| both, tree prediction | 184 | 92 | 4 (2.2%) | 2 (2.2%) | 1.6% | 85.3% | 4.43 | 10.62 |
| both, changed by the item (tree) | 2 | 2 | 0 (0.0%) | 0 (0.0%) | 42.1% | 0.0% | 4.07 | 4.09 |

* Cells that lost their estimate: 0 []
* W(a) on cells both estimate: median 1.000 (bar 1.30); cells whose prediction changed: 2.
* W(b) on NEW cells: median 1.33 (bar 2.0), p90 4.39 (bar 4.0); 52 cells.

NEW cells (template, actual / low / expected / high MiB):

* `v1|copy_fillna/mixed@1000000`: 88 / 99 / 99 / 115
* `v1|copy_fillna/mixed@2000000`: 176 / 198 / 198 / 231
* `v2|v2:copy_astype/mixed@1500000`: 110 / 109 / 115 / 148
* `v2|v2:copy_astype/mixed@3000000`: 208 / 203 / 208 / 296
* `v2|v2:copy_astype/num@1500000`: 122 / 120 / 126 / 159
* `v2|v2:copy_astype/num@3000000`: 231 / 226 / 230 / 319
* `v2|v2:copy_astype/text@1500000`: 98 / 97 / 103 / 136
* `v2|v2:copy_astype/text@3000000`: 185 / 180 / 185 / 273
* `v2|v2:load_fillna/text@1500000`: 287 / 247 / 319 / 1424
* `v2|v2:load_fillna/text@3000000`: 560 / 495 / 639 / 2848
* `v2|v2:text_fillna/text@1500000`: 41 / 46 / 46 / 46
* `v2|v2:text_fillna/text@3000000`: 81 / 92 / 92 / 92
* `v3|v3:astype_on_created/mixed@1250000`: 95 / 93 / 100 / 177
* `v3|v3:astype_on_created/mixed@2500000`: 173 / 170 / 177 / 355
* `v3|v3:astype_on_created/narrow@1250000`: 47 / 53 / 59 / 88
* `v3|v3:astype_on_created/narrow@2500000`: 93 / 89 / 96 / 176
* `v3|v3:astype_on_created/num@1250000`: 104 / 103 / 109 / 198
* `v3|v3:astype_on_created/num@2500000`: 193 / 189 / 196 / 397
* `v3|v3:astype_on_created/text@1250000`: 85 / 84 / 90 / 156
* `v3|v3:astype_on_created/text@2500000`: 154 / 151 / 158 / 313
* `v3|v3:astype_on_created/textwide@1250000`: 95 / 93 / 100 / 177
* `v3|v3:astype_on_created/textwide@2500000`: 174 / 170 / 177 / 355
* `v3|v3:astype_on_created/wide@1250000`: 143 / 141 / 147 / 282
* `v3|v3:astype_on_created/wide@2500000`: 269 / 265 / 272 / 565
* `v3|v3:copy_then_fillna/mixed@1250000`: 110 / 110 / 110 / 130
* `v3|v3:copy_then_fillna/mixed@2500000`: 219 / 219 / 219 / 260
* `v3|v3:copy_then_fillna/narrow@1250000`: 62 / 61 / 61 / 61  **ABOVE HIGH**
* `v3|v3:copy_then_fillna/narrow@2500000`: 124 / 122 / 122 / 122  **ABOVE HIGH**
* `v3|v3:copy_then_fillna/num@1250000`: 148 / 148 / 148 / 148  **ABOVE HIGH**
* `v3|v3:copy_then_fillna/num@2500000`: 296 / 296 / 296 / 296  **ABOVE HIGH**
* `v3|v3:copy_then_fillna/text@1250000`: 112 / 111 / 111 / 111  **ABOVE HIGH**
* `v3|v3:copy_then_fillna/text@2500000`: 224 / 222 / 222 / 222  **ABOVE HIGH**
* `v3|v3:copy_then_fillna/textwide@1250000`: 141 / 139 / 139 / 139  **ABOVE HIGH**
* `v3|v3:copy_then_fillna/textwide@2500000`: 282 / 279 / 279 / 279  **ABOVE HIGH**
* `v3|v3:copy_then_fillna/wide@1250000`: 272 / 272 / 272 / 272  **ABOVE HIGH**
* `v3|v3:copy_then_fillna/wide@2500000`: 544 / 544 / 544 / 544  **ABOVE HIGH**
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
