@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

call agent-run.env.cmd
pushd ".."
python utilities/gitea-pull-request.py --fork %GITEA_WORK_REPO_OWNER% --issue-json %ISSUE_FILENAME% --pr-json %WORK_REPORT_FILENAME% --head %GITEA_MAIN_HEAD% --repo "%GITEA_MAIN_REPO_OWNER%/%GITEA_MAIN_REPO_NAME%" --url %GITEA_INSTANCE% --token %GITEA_TOKEN%
popd
