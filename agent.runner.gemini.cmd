@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

pushd  "%~dp0"
python agent.py --config agent.gemini.json
popd

