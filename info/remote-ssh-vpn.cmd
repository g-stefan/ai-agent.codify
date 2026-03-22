@echo off
rem SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
rem SPDX-License-Identifier: Unlicense

set AUTH=--user %LLM_MACHINE_USERNAME% --password %LLM_MACHINE_PASSWORD% 
set SERVER_MARIADB=--forward 3306:127.0.0.1:3306
set SERVER_LLM_MODEL=--forward 48001:127.0.0.1:48001
set SERVER_LLM_EMBEDDING=--forward 48002:127.0.0.1:48002
set SERVER_LLM_RERANK=--forward 48003:127.0.0.1:48003
python remote-ssh-vpn.py %LLM_MACHINE_ADDRESS% --port %LLM_MACHINE_PORT% %AUTH% %SERVER_MARIADB% %SERVER_LLM_MODEL% %SERVER_LLM_EMBEDDING% %SERVER_LLM_RERANK%
