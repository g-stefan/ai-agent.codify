@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

llama-server -hf mradermacher/Qwen3-VL-Reranker-2B-i1-GGUF:Q4_K_M --reranking --pooling rank --ctx-size 32768 --batch-size 1024 --ubatch-size 1024 --cache-ram 0 --gpu-layers 28 --no-mmap --threads 8 --parallel 2 --temp 0.7 --top-p 0.95 --top-k 20 --min-p 0.00 --alias "Qwen3-VL-Reranker-2B" --port 48003
