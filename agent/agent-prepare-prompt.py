# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import requests
import json
import argparse
import sys
import os

PROMPT_BEGIN = os.getenv("PROMPT_BEGIN", "prompt.begin.md")
PROMPT_END = os.getenv("PROMPT_END", "prompt.end.md")
PROMPT_FILENAME = os.getenv("PROMPT_FILENAME", "prompt.md")
ISSUE_FILENAME = os.getenv("ISSUE_FILENAME", "issue.json")
WORK_WRITE = os.getenv("WORK_WRITE", "work.write")
GITEA_TOKEN = os.getenv("GITEA_TOKEN") # Retrieve the Gitea token

try:
    with open(PROMPT_BEGIN, "r", encoding="utf8") as f:
        promptBegin = f.read()
except Exception as e:
    print(f"Error reading file {PROMPT_BEGIN}: {e}", file=sys.stderr)
    sys.exit(1)

try:
    with open(PROMPT_END, "r", encoding="utf8") as f:
        promptEnd = f.read()
except Exception as e:
    print(f"Error reading file {PROMPT_END}: {e}", file=sys.stderr)
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
    with open(PROMPT_FILENAME, "w", encoding="utf8") as f:
        f.write(content)
except Exception as e:
    print(f"Error writing file {PROMPT_FILENAME}: {e}", file=sys.stderr)
    sys.exit(1)

# Collect all assets
assets = issueContent[0].get("assets", [])
for comment in issueComments:
    assetsList = comment.get("assets", [])
    for asset in assetsList:
        assets.append(asset)
        
# Download assets
if assets:
    # Ensure the WORK_WRITE/assets directory exists
    assets_dir = os.path.join(WORK_WRITE, "assets")
    try:
        os.makedirs(assets_dir, exist_ok=True)
    except Exception as e:
        print(f"Error creating assets directory {assets_dir}: {e}", file=sys.stderr)
        sys.exit(1)

    # Prepare HTTP headers with authorization token if available
    headers = {}
    if GITEA_TOKEN:
        headers["Authorization"] = f"token {GITEA_TOKEN}"

    for asset in assets:
        uuid = asset.get("uuid")
        name = asset.get("name", "")
        download_url = asset.get("browser_download_url")

        if not uuid or not download_url:
            print(f"Skipping asset missing UUID or download URL: {asset}", file=sys.stderr)
            continue

        # Extract file extension from the original file name
        _, ext = os.path.splitext(name)
        
        # Format the filename as {uuid}{ext}
        filename = f"{uuid}{ext}"
        filepath = os.path.join(assets_dir, filename)

        print(f"Downloading asset {name} -> {filepath}...")
        
        try:
            # Stream the file to handle potentially large assets efficiently
            response = requests.get(download_url, stream=True, headers=headers)
            
            # Check for HTTP errors (e.g. 401 Unauthorized, 403 Forbidden, 404 Not Found)
            if not response.ok:
                print(f"HTTP Error {response.status_code} when downloading {name}: {response.reason}", file=sys.stderr)
                if response.status_code in (401, 403):
                    print("Authorization error. Please verify that your GITEA_TOKEN is valid and has sufficient permissions.", file=sys.stderr)
                sys.exit(1) # Exit with error code 1 on bad HTTP response
            
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Successfully downloaded {filename}")
            
        except requests.exceptions.RequestException as e:
            print(f"Network error downloading asset {name}: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error saving asset {name}: {e}", file=sys.stderr)
            sys.exit(1)