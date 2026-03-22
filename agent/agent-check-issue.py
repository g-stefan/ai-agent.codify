# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import json
import sys
import os

GITEA_WORK_REPO_OWNER = os.getenv("GITEA_WORK_REPO_OWNER", "unknown")
ISSUE_FILENAME = os.getenv("ISSUE_FILENAME", "issue.json")

try:
    with open(ISSUE_FILENAME, "r", encoding="utf8") as f:
        issueContent = json.load(f)
except Exception as e:
    print(f"Error reading/parsing file {ISSUE_FILENAME}: {e}", file=sys.stderr)
    sys.exit(1)

issueComments = issueContent[0].get("issue_comments", [])
if len(issueComments) > 0:
    comment = issueComments[-1]
    if comment.get("user", {}).get("username", "") == GITEA_WORK_REPO_OWNER:
        print(f"Error: Work already done! Waiting for approval.", file=sys.stderr)
        sys.exit(1)
