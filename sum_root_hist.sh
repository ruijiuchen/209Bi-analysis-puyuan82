#!/bin/bash
# 完整示例（一行）
python sum_root_hist.py \
  --dir "./data" \
  --h2 "h2d" \
  --h1 "h_proj" \
  -o "sum_198Ir76.root" \
  --plot_dir "sum_198Ir76" \
  --t_min 0 \
  --t_max 3.0 \
  --z_min -0.0001 \
  --z_max 0.005 \
  --freq_low  309.5900e6 \
  --freq_high 309.6000e6 \
  --freq_tgt  309.5969e6 \
  --freq_lifetime 309.5969e6 \
  --freq_width_tgt 800 \
  --amp_threshold 0.02 \
  --no-logz \
  --no-correct-frequency
