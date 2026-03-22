# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import requests
import json
import argparse
import sys
import os
import subprocess

GITEA_MAIN_REPO_NAME=os.getenv("GITEA_MAIN_REPO_NAME", "unknown")
WORK_PATH=os.getenv("WORK_PATH", ".")
WORK_REPORT_FILENAME=os.getenv("WORK_REPORT_FILENAME", "work.json")

with open(WORK_REPORT_FILENAME, "r", encoding="utf8") as f:
    workContent = json.load(f)

currentPath=os.getcwd()
os.chdir(WORK_PATH+"/"+GITEA_MAIN_REPO_NAME)

# dont return on error
res = subprocess.run(
    [
        "git",
        "fetch",
        "--prune",
        "--prune-tags"
    ]
)

res = subprocess.run(
    [
        "git",
        "add",
        "--all"
    ]
)
if res.returncode != 0:
    sys.exit(res.returncode)

res = subprocess.run(
    [
        "git",
        "commit",
        "-m",
        workContent.get("title","Work done")
    ]
)
if res.returncode != 0:
    sys.exit(res.returncode)

res = subprocess.run(
    [
        "git",
        "push"
    ]
)
if res.returncode != 0:
    sys.exit(res.returncode)

os.chdir(currentPath)
