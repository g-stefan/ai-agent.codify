@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

set CUDA_VISIBLE_DEVICES=""
set LLAMA_ARG_N_GPU_LAYERS=0
llama-server -hf DevQuasar/Qwen.Qwen3-VL-Embedding-2B-GGUF:Q4_K_M --embedding --pooling none --no-warmup --ctx-size 32768 --batch-size 1024 --ubatch-size 1024 --image-min-tokens 1024 --cache-ram 0 --no-mmap --threads 8 --parallel 2 --temp 0.7 --top-p 0.95 --top-k 20 --min-p 0.00 --alias "Qwen3-VL-Embedding-2B" --port 48002

