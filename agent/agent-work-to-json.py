# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import json
import sys
import os

PROMPT_EXPERT_SESSION = os.getenv("PROMPT_EXPERT_SESSION", "session.json")
PROMPT_REPORT_JSON = os.getenv("PROMPT_REPORT_JSON", "report.json")
WORK_REPORT_FILENAME =  os.getenv("WORK_REPORT_FILENAME", "work.json")

try:
    with open(PROMPT_EXPERT_SESSION, "r", encoding="utf8") as f:
        sessionContent = json.load(f)
except Exception as e:
    print(f"Error reading/parsing file {PROMPT_EXPERT_SESSION}: {e}", file=sys.stderr)
    sys.exit(1)

try:
    with open(PROMPT_REPORT_JSON, "r", encoding="utf8") as f:
        promptReport = json.load(f)
except Exception as e:
    print(f"Error reading/parsing file {PROMPT_REPORT_JSON}: {e}", file=sys.stderr)
    sys.exit(1)


body = ""
for info in sessionContent:
    if info.get("role","") == "assistant":
        activity = info.get("content", None)
        if activity is not None:
            body += activity
            body += "\r\n"

data = {
    "title": promptReport.get("title", ""),
    "comment": promptReport.get("body", ""),
    "body": body
}

try:
    with open(WORK_REPORT_FILENAME, 'w', encoding='utf-8') as f:            
        json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Success! written '{WORK_REPORT_FILENAME}'.")
except IOError as e:
    print(f"Error writing to '{WORK_REPORT_FILENAME}': {e}", file=sys.stderr)
    sys.exit(1)
