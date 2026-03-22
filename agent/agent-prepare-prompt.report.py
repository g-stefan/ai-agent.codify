# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import requests
import json
import argparse
import sys
import os

PROMPT_REPORT_BEGIN = os.getenv("PROMPT_REPORT_BEGIN", "prompt.begin.md")
PROMPT_REPORT_END = os.getenv("PROMPT_REPORT_END", "prompt.end.md")
PROMPT_REPORT_FILENAME = os.getenv("PROMPT_REPORT_FILENAME", "prompt.md")
PROMPT_EXPERT_SESSION = os.getenv("PROMPT_EXPERT_SESSION", "session.json")

try:
    with open(PROMPT_REPORT_BEGIN, "r", encoding="utf8") as f:
        promptBegin = f.read()
except Exception as e:
    print(f"Error reading file {PROMPT_REPORT_BEGIN}: {e}", file=sys.stderr)
    sys.exit(1)

try:
    with open(PROMPT_REPORT_END, "r", encoding="utf8") as f:
        promptEnd = f.read()
except Exception as e:
    print(f"Error reading file {PROMPT_REPORT_END}: {e}", file=sys.stderr)
    sys.exit(1)

try:
    with open(PROMPT_EXPERT_SESSION, "r", encoding="utf8") as f:
        sessionContent = json.load(f)
except Exception as e:
    print(f"Error reading/parsing file {PROMPT_EXPERT_SESSION}: {e}", file=sys.stderr)
    sys.exit(1)

content = promptBegin

for info in sessionContent:
    if info.get("role","") == "assistant":
        activity = info.get("content", None)
        if activity is not None:
            content += activity
            content += "\r\n"
    
content += promptEnd

try:
    with open(PROMPT_REPORT_FILENAME, "w", encoding="utf8") as f:
        f.write(content)
except Exception as e:
    print(f"Error writing file {PROMPT_REPORT_FILENAME}: {e}", file=sys.stderr)
    sys.exit(1)
