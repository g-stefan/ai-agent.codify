@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

act-runner.exe register --config runner.config.json --no-interactive --instance %GITEA_INSTANCE% --token %GITEA_RUNNER_TOKEN%

