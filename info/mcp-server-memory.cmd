@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

set DB_HOST=127.0.0.1
set DB_PORT=3306
set DB_USER=root
set DB_PASS=
set DB_NAME=agent
set DB_TABLE=embeddings
set LLAMA_EMBED_URL=http://127.0.0.1:48002/embeddings
set LLAMA_RERANK_URL=http://127.0.0.1:48003/v1/rerank
set DB_SEARCH_LIMIT=8
set PORT=48101
set ENABLE_RERANKING=off
set MEMORY_DIR=memory
python mcp-server-memory.py
