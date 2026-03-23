@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

call agent-run.env.cmd
pushd ".."
python utilities/gitea-fork.py %GITEA_INSTANCE% %GITEA_MAIN_REPO_OWNER% %GITEA_MAIN_REPO_NAME% --token %GITEA_TOKEN% --ok-if-forked-already
popd
