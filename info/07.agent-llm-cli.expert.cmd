@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

call agent-run.env.cmd
python agent-llm-cli.py "%PROMPT_EXPERT_FILENAME%" --temp 0.7 --session "%PROMPT_EXPERT_SESSION%" --system "%PROMPT_EXPERT_SYSTEM%" --url "%LLM_SERVER%" --mcp "%MCP_MEMORY%" --mcp-env-base "MEMORY" --mcp "%MCP_WORKSPACE%" --mcp-env-base "WORKSPACE"
