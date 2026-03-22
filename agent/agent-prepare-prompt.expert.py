# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import requests
import json
import argparse
import sys
import os

PROMPT_EXPERT_BEGIN = os.getenv("PROMPT_EXPERT_BEGIN", "prompt.begin.md")
PROMPT_EXPERT_END = os.getenv("PROMPT_EXPERT_END", "prompt.end.md")
PROMPT_EXPERT_FILENAME = os.getenv("PROMPT_EXPERT_FILENAME", "prompt.md")
ISSUE_FILENAME = os.getenv("ISSUE_FILENAME", "issue.json")

try:
    with open(PROMPT_EXPERT_BEGIN, "r", encoding="utf8") as f:
        promptBegin = f.read()
except Exception as e:
    print(f"Error reading file {PROMPT_EXPERT_BEGIN}: {e}", file=sys.stderr)
    sys.exit(1)

try:
    with open(PROMPT_EXPERT_END, "r", encoding="utf8") as f:
        promptEnd = f.read()
except Exception as e:
    print(f"Error reading file {PROMPT_EXPERT_END}: {e}", file=sys.stderr)
    sys.exit(1)

try:
    with open(ISSUE_FILENAME, "r", encoding="utf8") as f:
        issueContent = json.load(f)
except Exception as e:
    print(f"Error reading/parsing file {ISSUE_FILENAME}: {e}", file=sys.stderr)
    sys.exit(1)

content = promptBegin
content += "## Issue by: " + issueContent[0].get("user", {}).get("username", "")
content += "\r\n"
content += "## Title: " + issueContent[0].get("title", "")
content += "\r\n"
content += issueContent[0].get("body", "")
content += "\r\n"

issueComments = issueContent[0].get("issue_comments", [])
for comment in issueComments:
    content += "## Comment by: " + comment.get("user", {}).get("username", "")
    content += "\r\n"
    content += comment.get("body", "")
    content += "\r\n"

content += promptEnd

try:
    with open(PROMPT_EXPERT_FILENAME, "w", encoding="utf8") as f:
        f.write(content)
except Exception as e:
    print(f"Error writing file {PROMPT_EXPERT_FILENAME}: {e}", file=sys.stderr)
    sys.exit(1)
