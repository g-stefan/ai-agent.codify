@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

call agent-run.env.cmd
python gitea-issues-comment.py --issue %ISSUE_FILENAME% --work %WORK_REPORT_FILENAME% --token %GITEA_TOKEN%
