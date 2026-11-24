# Phase 8b dev notebook set (`real_notebooks/`)

**Status: DEV ONLY.** A static AST census (`python tools/static_ops.py real_notebooks`) was run on these notebooks and
read on 2026-11-24, and it was used to set the v4 modelling priorities. They can never serve as held-out data. The
Phase 8b held-out set will be a fresh batch, sealed separately, with no census and no other inspection before the
freeze.

Not in git: the datasets (`real_notebooks/*.csv`, see `.gitignore`) and the notebooks (`*.ipynb` is ignored repo-wide).
This manifest pins their identity: anyone who rebuilds the folder checks the digests (`sha256sum real_notebooks/*`).
URLs are copied only from what the notebook files themselves state. "unknown" means the file does not say, and the
owner should fill it in. Nothing in this table was inferred.

| notebook | SHA-256 | source URL | dataset file | dataset SHA-256 | dataset URL |
|---|---|---|---|---|---|
| `notebook1.ipynb` | `535f049d9398b4886cd3438f5c557b486045f976a736f7a1716446dca64aeb62` | unknown | `dataset1.csv` (475,664,283 B; the notebook uploads a CSV in Colab) | `b19d39f515523373f991b689c07e11e7b0b95c17a2c27a87d91584ae16c5b040` | unknown |
| `notebook2.ipynb` | `7f936c4f700de491184c62bb1692aee598dae9ab0487e71cce47ac48fb71c5a6` | unknown | `dataset2.csv` (600,367 B; read as `messy_data.csv`) | `f56b1145ed0b650d4b1ef21329b9d61605b077000e7c63a2b8e6cea30588ee6c` | unknown |
| `notebook3.ipynb` | `1073bb3ef79689c1c97ae64da6fb86081fa279ce23a9bce11e973f05a7900564` | unknown | `dataset3.csv` (316,971 B; read as `healthcare-dataset-stroke-data.csv`) | `644d473b05d2797006bd94865e4f8bb057f0c721617911613c82c8fcfc707420` | unknown |
| `notebook4.ipynb` | `73f5b9ab7a37b418e52208afa5827396495054944ac55afe1bfa6f96a73a892d` | https://colab.research.google.com/github/satishgunjal/Real-Estate-Price-Prediction-Project/blob/master/House_Price_Prediction_Project.ipynb | `dataset4.csv` (938,020 B; read as `Bengaluru_House_Data.csv`) | `7b3e1361fcb64348d49eeb83d1e976738dc64bc978536df3438cf7b36f601b28` | https://www.kaggle.com/amitabhajoy/bengaluru-house-price-data |
| `notebook5.ipynb` | `29a110bec828fed8c71de0cd0b56f08a032680b1c3de9128f744fd3869108461` | unknown | `dataset5.csv` (7,077,973 B; loaded as `AB_NYC_2019.csv` via `kagglehub`) | `e420db40ff10fcb40efc1b5b1648ee0b18a48f4e4537155cecc59fe95d18783a` | https://www.kaggle.com/datasets/dgomonov/new-york-city-airbnb-open-data |

Notebook N goes with dataset N: each CSV's header matches the columns its notebook uses.
