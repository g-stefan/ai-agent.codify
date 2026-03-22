@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

rem required external env GITEA_TOKEN
set GITEA_INSTANCE=http://127.0.0.1:3000
set GITEA_MAIN_REPO_OWNER=g-stefan
set GITEA_MAIN_REPO_NAME=repo-101
set GITEA_MAIN_HEAD=main
set GITEA_WORK_REPO_OWNER=codify
set ISSUE_FILENAME=work.write\issue.json
set WORK_PATH=X:\Gitea
set WORK_READ=work.read
set WORK_WRITE=work.write
set WORK_REPORT=work.report

set LLM_SERVER=http://127.0.0.1:48001/v1/chat/completions

rem MCP over HTTP
rem set MCP_MEMORY=http://127.0.0.1:48101/mcp
rem set MCP_WORKSPACE=http://127.0.0.1:48102/mcp
rem set MCP_REPORT=http://127.0.0.1:48103/mcp

rem MCP over stdio

rem MCP Memory
set MEMORY_DB_HOST=127.0.0.1
set MEMORY_DB_PORT=3306
set MEMORY_DB_USER=root
set MEMORY_DB_PASS=
set MEMORY_DB_NAME=agent
set MEMORY_DB_TABLE=embeddings
set MEMORY_LLAMA_EMBED_URL=http://127.0.0.1:48002/embeddings
set MEMORY_LLAMA_RERANK_URL=http://127.0.0.1:48003/v1/rerank
set MEMORY_DB_SEARCH_LIMIT=8
set MEMORY_PORT=48101
set MEMORY_ENABLE_RERANKING=off
set MEMORY_MEMORY_DIR=memory
set MCP_MEMORY=python mcp-server-memory.py --stdio

rem MCP Workspace
set WORKSPACE_PORT=48102
set WORKSPACE_WORKSPACE_DIR=%WORK_PATH%\%GITEA_MAIN_REPO_NAME%
set WORKSPACE_HIDE_DOT_DIRS=true
set MCP_WORKSPACE=python mcp-server-workspace.py --stdio

rem MCP Report
set REPORT_PORT=48103
set REPORT_WORKSPACE_DIR=%WORK_REPORT%
set REPORT_HIDE_DOT_DIRS=true
set MCP_REPORT=python mcp-server-workspace.py --stdio

set PROMPT_EXPERT_SYSTEM=%WORK_READ%\system.expert-full-stack-web-engineer.memory-workspace.md
set PROMPT_EXPERT_BEGIN=%WORK_READ%\prompt.expert.begin.md
set PROMPT_EXPERT_END=%WORK_READ%\prompt.expert.end.md
set PROMPT_EXPERT_FILENAME=%WORK_WRITE%\prompt.expert.md
set PROMPT_EXPERT_SESSION=%WORK_WRITE%\prompt.expert.session.json

set PROMPT_REPORT_SYSTEM=%WORK_READ%\system.report-maker.workspace.md
set PROMPT_REPORT_BEGIN=%WORK_READ%\prompt.report.begin.md
set PROMPT_REPORT_END=%WORK_READ%\prompt.report.end.md
set PROMPT_REPORT_FILENAME=%WORK_WRITE%\prompt.report.md

set PROMPT_REPORT_OUTPUT=%WORK_REPORT%\report.md
set PROMPT_REPORT_JSON=%WORK_REPORT%\report.json
set WORK_REPORT_FILENAME=%WORK_REPORT%\work.json

