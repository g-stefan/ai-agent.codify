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
set DB_SEARCH_LIMIT=8
set PORT=48101
set MEMORY_DIR=memory
set WORKSPACE_DIR=workspace
python mcp-server-memory.py
