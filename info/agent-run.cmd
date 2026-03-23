@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

rem required external env GITEA_TOKEN
call agent-run.env.cmd

set AGENT_LOG=
rem set AGENT_LOG=--log "work.write\agent-run.log.jsonl"

pushd ".."

rem clean-up work writable folders
del /Q /F work.report\*
del /Q /F work.write\*

python agent/agent-run.py --config "work.read\agent-run.json" %AGENT_LOG%
popd
