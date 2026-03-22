@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

set PORT=48103
set WORKSPACE_DIR=work.report
set HIDE_DOT_DIRS=true
python mcp-server-workspace.py
