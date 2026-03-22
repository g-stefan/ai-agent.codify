# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import argparse
import json
import os
import sys
import requests

def create_pull_request(args):
    """
    Reads the PR data, constructs the API payload, and sends a POST request
    to the Gitea API to create a Pull Request. If the PR already exists, 
    adds the title and body as a comment instead.
    """
    pr_title = ""
    pr_body = ""

    # 1. Read the PR Title and Body from --pr-json
    if not os.path.exists(args.pr_json):
        print(f"Error: The PR JSON file '{args.pr_json}' does not exist.")
        sys.exit(1)
    try:
        with open(args.pr_json, 'r', encoding='utf-8') as f:
            pr_data = json.load(f)
            pr_title = pr_data.get("title")
            pr_body = pr_data.get("body")
            
            if not pr_title or pr_body is None:
                print(f"Error: The JSON file '{args.pr_json}' must contain both 'title' and 'body' keys.")
                sys.exit(1)
    except Exception as e:
        print(f"Error reading or parsing PR JSON file '{args.pr_json}': {e}")
        sys.exit(1)

    # 2. Link the issue
    # Get the issue number either from the direct argument or the JSON file
    issue_num = None
    if args.issue:
        # Strip the '#' if the user accidentally included it in the CLI arg
        issue_num = str(args.issue).lstrip('#')
    elif args.issue_json:
        if not os.path.exists(args.issue_json):
            print(f"Error: The JSON file '{args.issue_json}' does not exist.")
            sys.exit(1)
        try:
            with open(args.issue_json, 'r', encoding='utf-8') as jf:
                issue_data = json.load(jf)
                
                # The Gitea API might return a list of issues or a single issue object
                if isinstance(issue_data, list) and len(issue_data) > 0:
                    issue_num = str(issue_data[0].get('number', ''))                
                
                if not issue_num or issue_num == 'None':
                    print(f"Error: Could not find a valid 'number' in the JSON file '{args.issue_json}'.")
                    sys.exit(1)
        except Exception as e:
            print(f"Error reading or parsing JSON file '{args.issue_json}': {e}")
            sys.exit(1)

    # Append the issue link to the body if an issue number was found
    if issue_num:
        pr_body += f"\n\n---\n*Resolves #{issue_num}*"

    # 3. Setup authentication
    token = args.token or os.environ.get("GITEA_TOKEN")
    if not token:
        print("Error: Gitea API token is required.")
        print("Provide it via the --token argument or the GITEA_TOKEN environment variable.")
        sys.exit(1)

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    # 4. Construct API URL and Payload
    # Gitea API v1 pulls endpoint: POST /repos/{owner}/{repo}/pulls
    api_url = f"{args.url.rstrip('/')}/api/v1/repos/{args.repo}/pulls"

    # Format the head branch appropriately if it's coming from a fork
    head_value = f"{args.fork}:{args.head}" if args.fork else args.head

    payload = {
        "base": args.base,
        "head": head_value,
        "title": pr_title,
        "body": pr_body
    }

    # 5. Make the Request
    print(f"🚀 Creating PR on '{args.repo}' ({head_value} -> {args.base})...")
    
    try:
        response = requests.post(api_url, headers=headers, json=payload)
        
        # Check if the Pull Request already exists (HTTP 409 Conflict or 422 Unprocessable Entity)
        if response.status_code == 409 or (response.status_code == 422 and "already exists" in response.text.lower()):
            print("\n⚠️ Pull Request already exists. Adding title and body as a comment instead...")
            
            # Fetch existing PRs to find the specific PR number
            prs_resp = requests.get(f"{args.url.rstrip('/')}/api/v1/repos/{args.repo}/pulls?state=open", headers=headers)
            prs_resp.raise_for_status()
            
            existing_pr_num = None
            for pr in prs_resp.json():
                pr_head_ref = pr.get("head", {}).get("ref")
                pr_base_ref = pr.get("base", {}).get("ref")
                
                # Check if it matches our target branches
                is_match = False
                if pr_base_ref == args.base and pr_head_ref == args.head:
                    if args.fork:
                        pr_head_owner = pr.get("head", {}).get("repo", {}).get("owner", {}).get("login")
                        if pr_head_owner == args.fork:
                            is_match = True
                    else:
                        is_match = True
                        
                if is_match:
                    existing_pr_num = pr.get("number")
                    break
                    
            if not existing_pr_num:
                print("❌ Could not locate the existing open Pull Request to add a comment.")
                print(f"Original API Response: {response.text}")
                sys.exit(1)
                
            # Add the comment to the existing PR (PRs are treated as Issues for comments in Gitea)
            comment_url = f"{args.url.rstrip('/')}/api/v1/repos/{args.repo}/issues/{existing_pr_num}/comments"
            comment_payload = {
                "body": f"### {pr_title}\n\n{pr_body}"
            }
            comment_resp = requests.post(comment_url, headers=headers, json=comment_payload)
            comment_resp.raise_for_status()
            
            print(f"✅ Success! Added comment to existing PR #{existing_pr_num}.")
            print(f"🔗 PR URL:    {args.url.rstrip('/')}/{args.repo}/pulls/{existing_pr_num}")
            return # Exit successfully

        # If it wasn't a conflict error, raise exception for any other bad status codes
        response.raise_for_status()  
        
        pr_data = response.json()
        print("\n✅ Success! Pull Request created successfully.")
        print(f"🔗 PR URL:    {pr_data.get('html_url')}")
        print(f"🏷️  PR Number: #{pr_data.get('number')}")
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP Error creating Pull Request: {e}")
        if 'response' in locals() and hasattr(response, 'text'):
            print(f"API Response: {response.text}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Network error occurred: {e}")
        sys.exit(1)

def main():
    # Force UTF-8 encoding for standard output and error to prevent UnicodeEncodeError on Windows/legacy terminals
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    # Initialize
    parser = argparse.ArgumentParser(
        description="CLI tool to create a Gitea Pull Request or add a comment if it already exists."
    )
    
    # Required arguments
    parser.add_argument("--url", required=True, help="Base URL of your Gitea instance (e.g., https://gitea.example.com)")
    parser.add_argument("--repo", required=True, help="Repository path in the format 'owner/repo'")
    parser.add_argument("--head", required=True, help="The branch containing your commits (e.g., feature/new-login)")
    
    # Fork specific argument
    parser.add_argument("--fork", help="The owner of the fork repository if making a cross-repository PR (e.g., 'myuser')")
    
    # PR Content Argument (Required)
    parser.add_argument("--pr-json", required=True, help="Path to a JSON file containing the PR title and body. Format: {\"title\": \"...\", \"body\": \"...\"}")
    
    # Optional arguments
    parser.add_argument("--base", default="main", help="The branch you want to merge into (default: 'main')")
    parser.add_argument("--issue", help="Issue number to link to this PR (e.g., '42'). Mutually exclusive with --issue-json.")
    parser.add_argument("--issue-json", help="Path to a JSON file containing the Gitea API issue response to extract the issue number from.")
    parser.add_argument("--token", help="Gitea API token. You can also set the GITEA_TOKEN environment variable instead.")

    args = parser.parse_args()
    
    if args.issue and args.issue_json:
        print("Warning: Both --issue and --issue-json provided. --issue will take precedence.")
        
    create_pull_request(args)

if __name__ == "__main__":
    main()