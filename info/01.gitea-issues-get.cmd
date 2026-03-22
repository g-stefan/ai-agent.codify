@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

call agent-run.env.cmd
python gitea-issues-get.py --first-open --out %ISSUE_FILENAME% --assignee %GITEA_WORK_REPO_OWNER% --owner %GITEA_MAIN_REPO_OWNER% --repo %GITEA_MAIN_REPO_NAME% --url %GITEA_INSTANCE% --token %GITEA_TOKEN%
