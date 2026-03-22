# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

"""
Gitea Issue Comment (JSON Version)

This script reads an issue JSON file and a work JSON file, then posts
the work title and content as a comment to the issue using the Gitea API.

Prerequisites:
    pip install requests
"""

import os
import sys
import argparse
import requests
import json

def read_json_file(filepath):
    """Reads and parses a JSON file."""
    if not os.path.exists(filepath):
        print(f"Error: The file '{filepath}' does not exist.")
        sys.exit(1)
    
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception as e:
        print(f"Error reading or parsing JSON file '{filepath}': {e}")
        sys.exit(1)

def add_issue_comment(issue_url, comment_text, headers):
    """Posts a comment to the specified issue URL."""
    comments_url = f"{issue_url}/comments"
    
    # Ensure the comment is strictly a string to prevent Gitea 500 parsing errors.
    # If the JSON parsed it as a dictionary or list, we convert it to a string format.
    # We use ensure_ascii=False to prevent emojis/special chars from turning into \uXXXX escapes.
    if not isinstance(comment_text, str):
        comment_text = json.dumps(comment_text, indent=2, ensure_ascii=False)
        
    payload = {
        "body": comment_text
    }
    
    print(f"Posting comment to {comments_url}...")
    response = requests.post(comments_url, headers=headers, json=payload)
    
    if response.status_code == 201:
        print("Success! Comment successfully added to the issue.")
        comment_url = response.json().get('html_url', 'URL not available')
        print(f"View comment at: {comment_url}")
    else:
        print(f"Error posting comment: {response.status_code} - {response.text}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Add a solution to a Gitea issue using JSON inputs.")
    parser.add_argument("-i", "--issue", required=True, help="Path to the issue.json file")
    parser.add_argument("-w", "--work", required=True, help="Path to the work.json file")
    parser.add_argument("-t", "--token", help="Gitea API token. Can also be set via GITEA_TOKEN env variable.")
    
    args = parser.parse_args()
    
    # Resolve token (prefer CLI argument, fallback to environment variable)
    token = args.token or os.environ.get("GITEA_TOKEN")
    if not token:
        print("Error: Gitea API token is required. Use -t/--token or set the GITEA_TOKEN environment variable.")
        sys.exit(1)
        
    # Strip whitespace/newlines to prevent malformed HTTP request headers
    token = token.strip()
        
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8"
    }
    
    # 1. Read the JSON files
    issue_data = read_json_file(args.issue)
    work_data = read_json_file(args.work)
    
    # 2. Extract necessary data
    issue_url = issue_data[0].get("url")
    if not issue_url:
        print("Error: Invalid issue JSON format. Missing 'url' attribute.")
        sys.exit(1)
        
    work_comment = work_data.get("comment")
    if work_comment is None: 
        print("Error: Invalid work JSON format. Missing 'comment' attribute.")
        sys.exit(1)
        
    # Check if the comment is empty (handles empty strings, whitespace-only, empty lists/dicts)
    if isinstance(work_comment, str) and not work_comment.strip():
        print("The comment is empty. Skipping API post.")
        sys.exit(0)
    elif not isinstance(work_comment, str) and not work_comment:
        print("The comment is empty. Skipping API post.")
        sys.exit(0)
    
    print(f"Targeting issue #{issue_data[0].get('number', 'Unknown')}: '{issue_data[0].get('title', 'Unknown')}'")
    
    # 3. Post comment to the issue
    add_issue_comment(issue_url, work_comment, headers)

if __name__ == "__main__":
    main()