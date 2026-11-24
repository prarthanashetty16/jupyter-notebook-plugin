# Amendment 2 re-score (dev): displayed v4 high, item C factor fitted LOCO

Tree `content:7058cda30da623b3`; 524 dev points, 239 configurations. Displayed high = max(model high, expected x q), q from the item C procedure on every configuration except the scored one.

| group | cells | above model high | above displayed (LOCO) high | max actual / displayed high |
|---|---|---|---|---|
| item (1b): copy -> fillna cells | 14 | 10 | **0** | 0.859 |
| item (1a): the six flagged text_fillna_cols cells | 8 | 6 | **0** | 0.873 |
| all 52 cells new in v4 so far | 52 | 16 | **0** | 0.873 |

## Per cell (actual / expected / model high / displayed LOCO high, MiB)

* `v1|copy_fillna/mixed@1000000`: 87.9 / 99.2 / 115.4 / 118.1
* `v1|copy_fillna/mixed@2000000`: 175.8 / 198.4 / 230.8 / 236.3
* `v2|v2:copy_astype/mixed@1500000`: 110.1 / 114.9 / 147.9 / 147.9
* `v2|v2:copy_astype/mixed@3000000`: 208.4 / 207.5 / 295.7 / 295.7
* `v2|v2:copy_astype/num@1500000`: 121.6 / 126.4 / 159.3 / 159.3
* `v2|v2:copy_astype/num@3000000`: 231.3 / 230.4 / 318.6 / 318.6
* `v2|v2:copy_astype/text@1500000`: 98.5 / 103.5 / 136.4 / 136.4
* `v2|v2:copy_astype/text@3000000`: 185.5 / 184.6 / 272.9 / 272.9
* `v2|v2:load_fillna/text@1500000`: 286.7 / 319.3 / 1423.8 / 1423.8
* `v2|v2:load_fillna/text@3000000`: 560.2 / 638.9 / 2847.7 / 2847.7
* `v2|v2:text_fillna/text@1500000`: 40.6 / 45.8 / 45.8 / 54.5
* `v2|v2:text_fillna/text@3000000`: 80.6 / 91.6 / 91.6 / 109.0
* `v3|v3:astype_on_created/mixed@1250000`: 94.8 / 99.6 / 177.4 / 177.4
* `v3|v3:astype_on_created/mixed@2500000`: 173.1 / 176.7 / 354.8 / 354.8
* `v3|v3:astype_on_created/narrow@1250000`: 47.5 / 59.0 / 88.2 / 88.2
* `v3|v3:astype_on_created/narrow@2500000`: 92.9 / 95.6 / 176.4 / 176.4
* `v3|v3:astype_on_created/num@1250000`: 104.4 / 109.1 / 198.4 / 198.4
* `v3|v3:astype_on_created/num@2500000`: 193.1 / 195.8 / 396.7 / 396.7
* `v3|v3:astype_on_created/text@1250000`: 85.3 / 90.1 / 156.4 / 156.4
* `v3|v3:astype_on_created/text@2500000`: 154.3 / 157.6 / 312.8 / 312.8
* `v3|v3:astype_on_created/textwide@1250000`: 94.9 / 99.6 / 177.4 / 177.4
* `v3|v3:astype_on_created/textwide@2500000`: 174.0 / 176.7 / 354.8 / 354.8
* `v3|v3:astype_on_created/wide@1250000`: 142.6 / 147.3 / 282.3 / 282.3
* `v3|v3:astype_on_created/wide@2500000`: 269.4 / 272.1 / 564.6 / 564.6
* `v3|v3:copy_then_fillna/mixed@1250000`: 109.8 / 109.7 / 129.9 / 130.6
* `v3|v3:copy_then_fillna/mixed@2500000`: 219.5 / 219.3 / 259.9 / 261.3
* `v3|v3:copy_then_fillna/narrow@1250000`: 62.2 / 60.8 / 60.8 / 72.4
* `v3|v3:copy_then_fillna/narrow@2500000`: 124.2 / 121.6 / 121.6 / 144.8
* `v3|v3:copy_then_fillna/num@1250000`: 148.0 / 147.8 / 147.8 / 176.1
* `v3|v3:copy_then_fillna/num@2500000`: 295.8 / 295.6 / 295.6 / 352.1
* `v3|v3:copy_then_fillna/text@1250000`: 112.3 / 110.9 / 110.9 / 132.1
* `v3|v3:copy_then_fillna/text@2500000`: 224.3 / 221.7 / 221.7 / 264.1
* `v3|v3:copy_then_fillna/textwide@1250000`: 140.9 / 139.5 / 139.5 / 166.1
* `v3|v3:copy_then_fillna/textwide@2500000`: 281.5 / 278.9 / 278.9 / 332.3
* `v3|v3:copy_then_fillna/wide@1250000`: 272.0 / 271.8 / 271.8 / 323.7
* `v3|v3:copy_then_fillna/wide@2500000`: 543.8 / 543.6 / 543.6 / 647.5
* `v3|v3:load_fillna_text/mixed@1250000`: 252.1 / 311.2 / 1580.0 / 1580.0
* `v3|v3:load_fillna_text/mixed@2500000`: 499.6 / 622.5 / 3160.1 / 3160.1
* `v3|v3:load_fillna_text/narrow@1250000`: 183.4 / 185.6 / 684.7 / 684.7
* `v3|v3:load_fillna_text/narrow@2500000`: 324.4 / 371.0 / 1369.3 / 1369.3
* `v3|v3:load_fillna_text/text@1250000`: 250.0 / 266.3 / 1186.5 / 1186.5
* `v3|v3:load_fillna_text/text@2500000`: 471.4 / 532.5 / 2373.1 / 2373.1
* `v3|v3:load_fillna_text/textwide@1250000`: 357.7 / 341.2 / 1294.2 / 1294.2
* `v3|v3:load_fillna_text/textwide@2500000`: 659.3 / 685.7 / 2588.3 / 2588.3
* `v3|v3:text_fillna_cols/mixed@1250000`: 62.5 / 62.0 / 82.3 / 82.3
* `v3|v3:text_fillna_cols/mixed@2500000`: 124.5 / 124.0 / 164.5 / 164.5
* `v3|v3:text_fillna_cols/narrow@1250000`: 45.8 / 44.1 / 44.1 / 52.5
* `v3|v3:text_fillna_cols/narrow@2500000`: 91.1 / 88.2 / 88.2 / 105.1
* `v3|v3:text_fillna_cols/text@1250000`: 74.5 / 72.7 / 72.7 / 86.6
* `v3|v3:text_fillna_cols/text@2500000`: 148.4 / 145.4 / 145.4 / 173.2
* `v3|v3:text_fillna_cols/textwide@1250000`: 93.6 / 91.8 / 91.8 / 109.3
* `v3|v3:text_fillna_cols/textwide@2500000`: 186.5 / 183.6 / 183.6 / 218.7
