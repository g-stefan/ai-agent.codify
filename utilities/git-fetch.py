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
GITEA_MAIN_HEAD=os.getenv("GITEA_MAIN_HEAD", "main")
WORK_PATH=os.getenv("WORK_PATH", ".")

currentPath=os.getcwd()
os.chdir(WORK_PATH+"/"+GITEA_MAIN_REPO_NAME)

res = subprocess.run(
    [
        "git",
        "fetch",
        "--prune",
        "--prune-tags"
    ]
)
if res.returncode != 0:
    sys.exit(res.returncode)

res = subprocess.run(
    [
        "git",
        "pull",
        "upstream",
        GITEA_MAIN_HEAD,
        "--allow-unrelated-histories",
        "--no-commit"
    ]
)
if res.returncode != 0:
    sys.exit(res.returncode)

res = subprocess.run(
    [
        "git",
        "commit",
        "-m",
        "Upstream"
    ]
)
if res.returncode != 0:
    sys.exit(res.returncode)

res = subprocess.run(
    [
        "git",
        "push",
        "origin",
        GITEA_MAIN_HEAD
    ]
)
if res.returncode != 0:
    sys.exit(res.returncode)

os.chdir(currentPath)
