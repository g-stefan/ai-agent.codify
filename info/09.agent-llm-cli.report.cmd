@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

call agent-run.env.cmd
python agent-llm-cli.py --temp 0.7 %PROMPT_REPORT_FILENAME% --system %PROMPT_REPORT_SYSTEM% --url %LLM_SERVER% --mcp "%MCP_REPORT%" --mcp-env-base "REPORT"
