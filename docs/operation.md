# Automated Agent Operation Pipeline (`agent-run.json`)

## Overview
This document describes the operational pipeline defined in `work.read/agent-run.json`. This JSON configuration is executed by the `agent-run.py` task runner and orchestrates a complete lifecycle for an autonomous AI developer agent.

The pipeline performs everything from discovering assigned issues on a Gitea instance to setting up a local Git environment, generating code solutions via an LLM, synthesizing a report, and finally pushing the code and opening a Pull Request.

## Execution Steps

### Phase 1: Issue Discovery and Validation
**1. Fetch Assigned Issues (`gitea-issues-get`)**
*   **Action:** The script connects to the Gitea instance and searches for the **first open issue** assigned to the agent (`$GITEA_WORK_REPO_OWNER`).
*   **Behavior:** If no issue is found, the command fails but gracefully exits the pipeline (code 0) due to `"error-exit-ok": true`. The retrieved issue data (including comments) is saved to `$ISSUE_FILENAME`.

**2. Verify Work Status (`agent-check-issue.py`)**
*   **Action:** Reads the fetched issue JSON to check the comment history.
*   **Behavior:** If the most recent comment on the issue was posted by the agent itself, it assumes the work is already done and awaiting human review. It will halt the pipeline here but exit gracefully (`"error-exit-ok": true`).

### Phase 2: Workspace Setup
**3. Fork Repository (`gitea-fork`)**
*   **Action:** Ensures the agent has a personal fork of the target repository (`$GITEA_MAIN_REPO_NAME`).
*   **Behavior:** Uses the `--ok-if-forked-already` flag so it safely skips this step if the fork already exists.

**4. Clone Repository (`git-clone`)**
*   **Action:** Performs a shallow clone of the agent's fork into the local workspace and configures the upstream remote.
*   **Behavior:** This step is marked `"required": false`, meaning if the folder already exists (clone fails), the pipeline will continue.

**5. Sync with Upstream (`git-fetch`)**
*   **Action:** Fetches the latest changes from the main repository's upstream branch and merges them into the agent's local fork.
*   **Behavior:** Also marked `"required": false`, allowing the pipeline to proceed even if the sync encounters minor git errors.

### Phase 3: Expert Code Generation
**6. Prepare Expert Prompt (`agent-prepare-prompt.expert`)**
*   **Action:** Assembles a comprehensive Markdown prompt (`$PROMPT_EXPERT_FILENAME`) combining static system instructions with the dynamic issue title, body, and comment history extracted in Phase 1.

**7. Execute Expert LLM (`agent-llm-cli.expert`)**
*   **Action:** Feeds the prepared prompt to the main "Expert" AI model using `agent-llm-cli.py`.
*   **Behavior:** The LLM is connected to two MCP servers—Memory and Workspace—allowing it to actively search the codebase, read files, and write code modifications to resolve the issue. The entire multi-turn chat interaction is saved to `$PROMPT_EXPERT_SESSION`.

### Phase 4: Reporting and Consolidation
**8. Prepare Report Prompt (`agent-prepare-prompt.report`)**
*   **Action:** Reads the saved Expert session and extracts all actions taken by the AI assistant. It packages these into a new prompt designed to generate a concise human-readable summary.

**9. Execute Reporting LLM (`agent-llm-cli.report`)**
*   **Action:** Sends the report prompt to the LLM (with its own isolated MCP environment) to synthesize a clean summary of the work done.

**10. Format Report to JSON (`agent-report-to-json`)**
*   **Action:** Converts the raw Markdown summary output into a structured JSON file (`$PROMPT_REPORT_JSON`) containing a `"title"` and `"body"`.

**11. Consolidate Work Payload (`agent-work-to-json.py`)**
*   **Action:** Merges the raw expert session logs with the clean summary JSON into a final comprehensive payload (`$WORK_REPORT_FILENAME`), establishing exactly what was done and the narrative to present to humans.

### Phase 5: Submission
**12. Commit and Push (`git-push`)**
*   **Action:** Stages all modified files in the local workspace, commits them using the title from the consolidated work payload, and pushes the changes to the agent's remote fork.

**13. Comment on Issue (`gitea-issues-comment`)**
*   **Action:** Posts the detailed body of the consolidated work payload as a comment on the original Gitea issue, notifying reviewers that work has been attempted.

**14. Open Pull Request (`gitea-pull-request`)**
*   **Action:** Submits a Pull Request from the agent's fork to the upstream main repository.
*   **Behavior:** It uses the title and body from `$WORK_REPORT_FILENAME` and links the PR directly to the original issue (`$ISSUE_FILENAME`). If a PR already exists for this branch, it seamlessly adds the new payload as a comment to the existing PR instead.