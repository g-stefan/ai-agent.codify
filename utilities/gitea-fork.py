# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

def main():
    # Force UTF-8 encoding for standard output and error to prevent UnicodeEncodeError on Windows/legacy terminals
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    # Initialize    
    parser = argparse.ArgumentParser(
        description="Fork a repository on a Gitea instance via the API.",
        epilog="Example: python gitea_fork.py https://gitea.com gitea go-gitea --token my_token123"
    )
    
    # Positional Arguments
    parser.add_argument("url", help="Base URL of the Gitea instance (e.g., https://gitea.example.com)")
    parser.add_argument("owner", help="The owner of the original repository")
    parser.add_argument("repo", help="The name of the repository to fork")
    
    # Optional Arguments
    parser.add_argument("-t", "--token", 
                        help="Your Gitea API token. Alternatively, set the GITEA_TOKEN environment variable.", 
                        default=os.environ.get("GITEA_TOKEN"))
    parser.add_argument("-o", "--org", 
                        help="Optional: The organization to fork the repository into. If omitted, forks to the current user.",
                        default=None)
    parser.add_argument("--ok-if-forked-already", 
                        action="store_true",
                        help="If the repository is already forked, exit successfully instead of returning an error.")

    args = parser.parse_args()

    # Ensure token is provided
    if not args.token:
        print("Error: Gitea API token is required.", file=sys.stderr)
        print("Provide it via the --token argument or the GITEA_TOKEN environment variable.", file=sys.stderr)
        sys.exit(1)

    # Format the API URL
    base_url = args.url.rstrip('/')
    api_endpoint = f"{base_url}/api/v1/repos/{args.owner}/{args.repo}/forks"

    # Set up HTTP headers for authentication and JSON payload
    headers = {
        "Authorization": f"token {args.token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Set up the payload (Gitea allows specifying a target organization in the body)
    payload = {}
    if args.org:
        payload["organization"] = args.org

    json_data = json.dumps(payload).encode("utf-8")

    # Create the Request object
    req = urllib.request.Request(api_endpoint, data=json_data, headers=headers, method="POST")

    print(f"Attempting to fork {args.owner}/{args.repo} on {base_url}...")

    # Execute the request
    try:
        with urllib.request.urlopen(req) as response:
            if response.status in (201, 202):
                res_data = json.loads(response.read().decode("utf-8"))
                fork_url = res_data.get("html_url", "URL not provided in response")
                print(f"Success! Repository successfully forked to: {fork_url}")
            else:
                print(f"Unexpected status code received: {response.status}")
                
    except urllib.error.HTTPError as e:
        # Gitea returns 409 Conflict if the repository is already forked to the target user/org
        if e.code == 409 and args.ok_if_forked_already:
            print(f"Notice: Repository '{args.owner}/{args.repo}' is already forked. Exiting successfully as requested.")
            sys.exit(0)

        # Handle HTTP errors (e.g., 401 Unauthorized, 404 Not Found, 409 Conflict)
        error_body = e.read().decode("utf-8")
        print(f"\nFailed to fork repository. HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        
        try:
            # Try to parse the Gitea API error message if it's JSON
            err_json = json.loads(error_body)
            print(f"Gitea API Message: {err_json.get('message', error_body)}", file=sys.stderr)
        except json.JSONDecodeError:
            print(f"Details: {error_body}", file=sys.stderr)
            
        sys.exit(1)
        
    except urllib.error.URLError as e:
        # Handle network errors (e.g., bad URL, DNS issues)
        print(f"\nFailed to connect to the Gitea instance: {e.reason}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()