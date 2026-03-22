@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

llama-server -hf unsloth/Qwen3.5-35B-A3B-GGUF:UD-Q3_K_XL --ctx-size 262144 --cache-ram 1024 --batch-size 1024 --ubatch-size 1024 --image-min-tokens 1024 --threads 8 --parallel 2 --temp 0.7 --top-p 0.95 --top-k 20 --min-p 0.00 --alias "Qwen3.5-35B-A3B" --port 48001
