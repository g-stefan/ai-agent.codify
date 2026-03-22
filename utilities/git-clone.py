# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import requests
import json
import argparse
import sys
import os
import subprocess

WORK_PATH=os.getenv("WORK_PATH", ".")
GITEA_INSTANCE=os.getenv("GITEA_INSTANCE", "https://127.0.0.1")
GITEA_MAIN_REPO_OWNER=os.getenv("GITEA_MAIN_REPO_OWNER", "unknown")
GITEA_WORK_REPO_OWNER=os.getenv("GITEA_WORK_REPO_OWNER", "unknown")
GITEA_MAIN_REPO_NAME=os.getenv("GITEA_MAIN_REPO_NAME", "unknown")
GITEA_MAIN_HEAD=os.getenv("GITEA_MAIN_HEAD", "main")

currentPath=os.getcwd()
os.chdir(WORK_PATH)

res = subprocess.run(
    [
        "git",
        "clone",
        "--depth=1",
        GITEA_INSTANCE+"/"+GITEA_WORK_REPO_OWNER+"/"+GITEA_MAIN_REPO_NAME
    ]
)
if res.returncode != 0:
    sys.exit(res.returncode)

os.chdir(WORK_PATH+"/"+GITEA_MAIN_REPO_NAME)

res = subprocess.run(
    [
        "git",
        "remote",
        "add",
        "upstream",
        "-t",
        GITEA_MAIN_HEAD,
        GITEA_INSTANCE+"/"+GITEA_MAIN_REPO_OWNER+"/"+GITEA_MAIN_REPO_NAME
    ]
)
if res.returncode != 0:
    sys.exit(res.returncode)

os.chdir(currentPath)
