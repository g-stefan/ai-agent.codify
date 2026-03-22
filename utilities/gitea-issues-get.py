# Codify
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import requests
import json
import argparse
import sys
import os

class GiteaClient:
    """A simple client to interact with the Gitea API."""
    
    def __init__(self, base_url, token):
        # Ensure the base URL doesn't have a trailing slash for consistent formatting
        self.base_url = base_url.rstrip('/')
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/json'
        }

    def get_all_issues(self, owner, repo):
        """Fetches all issues (open and closed) for a given repository."""
        print(f"Fetching all issues for {owner}/{repo}...")
        issues = []
        page = 1
        limit = 50 # Max items per page
        
        while True:
            url = f"{self.base_url}/api/v1/repos/{owner}/{repo}/issues"
            params = {
                'state': 'all',
                'page': page,
                'limit': limit
            }
            
            try:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status() # Raise an exception for bad status codes
                
                data = response.json()
                if not data:
                    break # Break the loop if the page is empty
                    
                issues.extend(data)
                print(f"  - Retrieved page {page} ({len(data)} issues)")
                page += 1
                
            except requests.exceptions.RequestException as e:
                print(f"Error fetching issues: {e}")
                sys.exit(1)
                
        return issues

    def get_single_issue(self, owner, repo, issue_index):
        """Fetches a specific issue by its index number."""
        print(f"Fetching issue #{issue_index} for {owner}/{repo}...")
        url = f"{self.base_url}/api/v1/repos/{owner}/{repo}/issues/{issue_index}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching issue #{issue_index}: {e}")
            if response.status_code == 404:
                print("Issue not found. Please check the issue number.")
            sys.exit(1)

    def get_first_open_issue(self, owner, repo):
        """Fetches the first found open issue."""
        print(f"Fetching first open issue for {owner}/{repo}...")
        url = f"{self.base_url}/api/v1/repos/{owner}/{repo}/issues"
        params = {
            'state': 'open',
            'limit': 1,
            'page': 1,
            'type': 'issues' # Filters out pull requests
        }
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            return data[0] if data else None
        except requests.exceptions.RequestException as e:
            print(f"Error fetching first open issue: {e}")
            sys.exit(1)

    def get_open_issues_by_assignee(self, owner, repo, assignee_username, first_open=False):
        """Fetches all open issues and filters them by a specific assignee username."""
        print(f"Fetching open issues assigned to '{assignee_username}' for {owner}/{repo}...")
        assigned_issues = []
        page = 1
        limit = 50
        
        while True:
            url = f"{self.base_url}/api/v1/repos/{owner}/{repo}/issues"
            params = {
                'state': 'open',
                'page': page,
                'limit': limit,
                'type': 'issues'
            }
            
            try:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                if not data:
                    break
                    
                for issue in data:
                    # Collect all usernames assigned to this issue
                    assignees_list = issue.get('assignees', [])
                    if assignees_list is None:
                        assignees_list = []
                        
                    assignee_logins = [a.get('login') for a in assignees_list if isinstance(a, dict)]
                    
                    # Also check the singular 'assignee' field for older Gitea versions
                    single_assignee = issue.get('assignee')
                    if single_assignee and isinstance(single_assignee, dict):
                        login = single_assignee.get('login')
                        if login and login not in assignee_logins:
                            assignee_logins.append(login)
                            
                    # Check if our target username is in the collected list
                    if assignee_username in assignee_logins:
                        assigned_issues.append(issue)
                        if first_open:
                            print(f"  - Found the first open issue assigned to '{assignee_username}' (Issue #{issue.get('number')})")
                            return assigned_issues
                        
                print(f"  - Scanned page {page} ({len(data)} open issues)")
                page += 1
                
            except requests.exceptions.RequestException as e:
                print(f"Error fetching issues: {e}")
                sys.exit(1)
                
        return assigned_issues

    def get_issue_comments(self, owner, repo, issue_index):
        """Fetches all comments (history/chat) for a specific issue."""
        print(f"Fetching comments history for issue #{issue_index}...")
        comments = []
        seen_ids = set()
        page = 1
        limit = 50
        
        while True:
            url = f"{self.base_url}/api/v1/repos/{owner}/{repo}/issues/{issue_index}/comments"
            params = {
                'page': page,
                'limit': limit
            }
            
            try:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                if not data:
                    break # Break the loop if there are no more comments
                    
                # Safeguard: prevent infinite loops if the API ignores 'page' param
                added_new = False
                for comment in data:
                    c_id = comment.get('id')
                    # Track by ID to ensure we don't process the same data endlessly
                    if c_id not in seen_ids:
                        comments.append(comment)
                        if c_id is not None:
                            seen_ids.add(c_id)
                        added_new = True
                        
                if not added_new:
                    break # Break if we didn't find any new comments on this page
                    
                page += 1
                
            except requests.exceptions.RequestException as e:
                print(f"Error fetching comments: {e}")
                break # We just break so we don't completely kill the script if comments fail
                
        return comments

def save_to_json(data, filename):
    """Saves Python dictionaries/lists to a formatted JSON file."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Successfully saved data to '{os.path.abspath(filename)}'")
    except IOError as e:
        print(f"Error saving file: {e}")

def main():
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(description="Export issues from a Gitea repository to JSON.")
    parser.add_argument("--url", required=True, help="Base URL of the Gitea server (e.g., https://gitea.example.com)")
    parser.add_argument("--token", required=True, help="Your Gitea personal access token")
    parser.add_argument("--owner", required=True, help="The owner (user or organization) of the repository")
    parser.add_argument("--repo", required=True, help="The name of the repository")
    parser.add_argument("--issue", type=int, help="Optional: Specify a single issue index to download just that issue")
    parser.add_argument("--assignee", help="Optional: Return only open issues assigned to this username")
    parser.add_argument("--out", default=None, help="Optional: Output JSON filename (default varies based on mode)")
    parser.add_argument("--first-open", action="store_true", help="Optional: Fetch the first open issue and save it to JSON")
    parser.add_argument("--error-on-no-issue", action="store_true", help="Optional: exit with error if no issue is found")

    args = parser.parse_args()

    # Initialize the client
    client = GiteaClient(args.url, args.token)

    # Determine what mode we are running in based on provided arguments
    if args.assignee:
        # Fetch open issues assigned to a specific user
        issues_data = client.get_open_issues_by_assignee(args.owner, args.repo, args.assignee, first_open=args.first_open)
        
        if not issues_data:
            print(f"No open issues found assigned to '{args.assignee}'.")
            if args.error_on_no_issue:
                sys.exit(1)
        else:
            print(f"Total assigned issues retrieved: {len(issues_data)}")
            
            # Fetch comments for each assigned issue so all chat history is saved
            print("Fetching comments for all matched issues...")
            for issue in issues_data:
                number = issue.get('number')
                if number:
                    comments = client.get_issue_comments(args.owner, args.repo, number)
                    issue['issue_comments'] = comments
            
            # Determine the filename dynamically
            out_filename = args.out if args.out else f"{args.repo}_assigned_to_{args.assignee}.json"
            save_to_json(issues_data, out_filename)

    elif args.first_open:
        # Fetch the first open issue
        issue_data = client.get_first_open_issue(args.owner, args.repo)
        
        if issue_data:
            number = issue_data.get('number', 'unknown')
            
            # Fetch the comment history for the open issue
            comments = client.get_issue_comments(args.owner, args.repo, number)
            
            # Inject the comments into the JSON payload before saving
            issue_data['issue_comments'] = comments
            
            # Determine the filename dynamically if not provided
            out_filename = args.out if args.out else f"issue_{number}.json"
            save_to_json([issue_data], out_filename)
        else:
            print("No open issues found in this repository.")
            if args.error_on_no_issue:
                sys.exit(1)
            
    elif args.issue:
        # Fetch a single issue
        issue_data = client.get_single_issue(args.owner, args.repo, args.issue)
        
        # Determine the filename dynamically
        out_filename = args.out if args.out else f"issue_{args.issue}.json"
        save_to_json([issue_data], out_filename)
        
    else:
        # Fetch all issues
        issues_data = client.get_all_issues(args.owner, args.repo)
        
        if not issues_data:
            print("No issues found in this repository.")
            if args.error_on_no_issue:
                sys.exit(1)
        else:
            print(f"Total issues retrieved: {len(issues_data)}")
            
            # Determine the filename dynamically
            out_filename = args.out if args.out else f"{args.repo}_all_issues.json"
            save_to_json(issues_data, out_filename)

if __name__ == "__main__":
    main()