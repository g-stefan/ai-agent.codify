# MCP Task
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import json
import argparse
import sqlite3
from typing import List, Dict, Any

import uvicorn
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

# Gracefully handle MariaDB import so the server can run on pure SQLite setups
try:
    import mariadb
except ImportError:
    mariadb = None

# --- Pre-parse --env-base, --read-only and DB args ---
pre_parser = argparse.ArgumentParser(add_help=False)
pre_parser.add_argument("--env-base", type=str, default="")
pre_parser.add_argument("--read-only", action="store_true")
pre_parser.add_argument("--tool-prefix", type=str, default="")
pre_parser.add_argument("--mcp-name", type=str, default="Tasks")
pre_parser.add_argument("--db-type", type=str, default="sqlite", choices=["mariadb", "sqlite"])
pre_parser.add_argument("--sqlite-db", type=str, default=".codify/task.sqlite")
pre_args, _ = pre_parser.parse_known_args()

ENV_PREFIX = pre_args.env_base
READ_ONLY = pre_args.read_only
TOOL_PREFIX = pre_args.tool_prefix
MCP_NAME = pre_args.mcp_name


def get_env_var(name: str, default: Any = None) -> Any:
    """Get an environment variable, optionally applying the env-base prefix."""
    if ENV_PREFIX:
        prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        env_key = f"{prefix}{name}"
    else:
        env_key = name
    return os.environ.get(env_key, default)


# Initialize the MCP Server
mcp = FastMCP(MCP_NAME, stateless_http=True, json_response=False)

# Configuration via Environment Variables
DB_TYPE = get_env_var("DB_TYPE", pre_args.db_type).lower()
SQLITE_DB = get_env_var("SQLITE_DB", pre_args.sqlite_db)
PORT = int(get_env_var("PORT", 48102))
DB_HOST = get_env_var("DB_HOST", "127.0.0.1")
DB_PORT = int(get_env_var("DB_PORT", 3306))
DB_USER = get_env_var("DB_USER", "root")
DB_PASS = get_env_var("DB_PASS", "")
DB_NAME = get_env_var("DB_NAME", "task_manager")

def get_db_connection():
    """Helper to get database connection (MariaDB or SQLite)."""
    if DB_TYPE == "sqlite":
        # Ensure the target directory for SQLite database exists
        db_dir = os.path.dirname(SQLITE_DB)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
            
        conn = sqlite3.connect(SQLITE_DB, timeout=10.0)
        # Enable foreign key constraints in SQLite
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    else:
        if mariadb is None:
            raise RuntimeError("MariaDB driver is not installed. Please install mariadb or use DB_TYPE=sqlite.")
        
        kwargs = {"host": DB_HOST, "port": DB_PORT, "user": DB_USER, "database": DB_NAME}
        if DB_PASS:
            kwargs["password"] = DB_PASS
        return mariadb.connect(**kwargs)

def format_row_to_dict(cursor, row):
    """Helper to convert a DB row to a dictionary using cursor description."""
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))

# --- Database Init Helper ---
def initialize_database():
    """Ensure tables exist (optional fail-safe if schema.sql wasn't run manually)."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if DB_TYPE == "sqlite":
            # Ensure project table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS project (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'active',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Ensure task table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS task (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    parent_task_id INTEGER DEFAULT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'pending',
                    priority INTEGER DEFAULT 0,
                    task_order INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES project (id) ON DELETE CASCADE,
                    FOREIGN KEY (parent_task_id) REFERENCES task (id) ON DELETE CASCADE
                )
            """)
            # SQLite Triggers to emulate ON UPDATE CURRENT_TIMESTAMP
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_project_updated_at
                AFTER UPDATE ON project
                BEGIN
                    UPDATE project SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END;
            """)
            cur.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_task_updated_at
                AFTER UPDATE ON task
                BEGIN
                    UPDATE task SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END;
            """)
            # Performance Indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_task_project ON task (project_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_task_parent ON task (parent_task_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_task_status ON task (status)")
            
        else:
            # MariaDB / MySQL Initialization
            cur.execute("""
                CREATE TABLE IF NOT EXISTS `project` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `name` VARCHAR(255) NOT NULL,
                    `description` TEXT,
                    `status` VARCHAR(50) DEFAULT 'active',
                    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS `task` (
                    `id` INT AUTO_INCREMENT PRIMARY KEY,
                    `project_id` INT NOT NULL,
                    `parent_task_id` INT DEFAULT NULL,
                    `title` VARCHAR(255) NOT NULL,
                    `description` TEXT,
                    `status` VARCHAR(50) DEFAULT 'pending',
                    `priority` INT DEFAULT 0,
                    `task_order` INT DEFAULT 0,
                    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (`project_id`) REFERENCES `project` (`id`) ON DELETE CASCADE,
                    FOREIGN KEY (`parent_task_id`) REFERENCES `task` (`id`) ON DELETE CASCADE
                )
            """)
            
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database initialization error (or tables exist): {e}", file=sys.stderr)

# Run init immediately
initialize_database()

# --- MCP Tools ---

# ----------------- Write Operations -----------------
if not READ_ONLY:

    @mcp.tool(name=f"{TOOL_PREFIX}project_create")
    async def project_create(name: str, description: str = "") -> str:
        """Create a new project."""
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO project (name, description, status) VALUES (?, ?, 'active')", 
                (name, description)
            )
            
            if DB_TYPE == "sqlite":
                project_id = cur.lastrowid
            else:
                cur.execute("SELECT LAST_INSERT_ID()")
                project_id = cur.fetchone()[0]
                
            conn.commit()
            conn.close()
            return f"Project '{name}' successfully created with ID: {project_id}."
        except Exception as e:
            return f"Error creating project: {str(e)}"

    @mcp.tool(name=f"{TOOL_PREFIX}project_delete")
    async def project_delete(project_id: int) -> str:
        """Delete a project and all its associated tasks (cascade delete)."""
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM project WHERE id = ?", (project_id,))
            affected = cur.rowcount
            conn.commit()
            conn.close()
            if affected > 0:
                return f"Successfully deleted project ID: {project_id}."
            return f"Project ID {project_id} not found."
        except Exception as e:
            return f"Error deleting project: {str(e)}"

    @mcp.tool(name=f"{TOOL_PREFIX}task_add")
    async def task_add(project_id: int, title: str, description: str = "", parent_task_id: int = 0, priority: int = 0, task_order: int = 0) -> str:
        """
        Add a task to a project.
        - project_id: The ID of the project
        - title: Name of the task
        - parent_task_id (optional): Use this to make it a subtask of another task. Send 0 to keep it as a root task.
        - priority (optional): Integer priority (higher is more important).
        - task_order (optional): Execution order (lower is earlier).
        """
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            p_id = parent_task_id if parent_task_id > 0 else None
            
            cur.execute(
                "INSERT INTO task (project_id, parent_task_id, title, description, priority, task_order, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')", 
                (project_id, p_id, title, description, priority, task_order)
            )
            
            if DB_TYPE == "sqlite":
                task_id = cur.lastrowid
            else:
                cur.execute("SELECT LAST_INSERT_ID()")
                task_id = cur.fetchone()[0]
                
            conn.commit()
            conn.close()
            
            rel_str = f" (Subtask of {p_id})" if p_id else ""
            return f"Task '{title}' successfully added with ID: {task_id}{rel_str}."
        except Exception as e:
            return f"Error adding task: {str(e)}"

    @mcp.tool(name=f"{TOOL_PREFIX}task_update")
    async def task_update(task_id: int, title: str = "", description: str = "", status: str = "", priority: int = -1, task_order: int = -1) -> str:
        """
        Update the status, title, description, priority, or task_order of a task/subtask. 
        Only non-empty fields will be updated. Valid statuses: 'pending', 'in_progress', 'blocked', 'completed'.
        """
        try:
            updates = []
            values = []
            
            if title:
                updates.append("title = ?")
                values.append(title)
            if description:
                updates.append("description = ?")
                values.append(description)
            if status:
                updates.append("status = ?")
                values.append(status)
            if priority >= 0:
                updates.append("priority = ?")
                values.append(priority)
            if task_order >= 0:
                updates.append("task_order = ?")
                values.append(task_order)
                
            if not updates:
                return "No valid fields provided to update."
                
            values.append(task_id) # For the WHERE clause
            
            query = f"UPDATE task SET {', '.join(updates)} WHERE id = ?"
            
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(query, tuple(values))
            affected = cur.rowcount
            conn.commit()
            conn.close()
            
            if affected > 0:
                return f"Task {task_id} successfully updated."
            return f"Task {task_id} not found or no changes made."
        except Exception as e:
            return f"Error updating task: {str(e)}"

    @mcp.tool(name=f"{TOOL_PREFIX}task_delete")
    async def task_delete(task_id: int) -> str:
        """Delete a specified task and any of its subtasks."""
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM task WHERE id = ?", (task_id,))
            affected = cur.rowcount
            conn.commit()
            conn.close()
            
            if affected > 0:
                return f"Successfully deleted task ID: {task_id}."
            return f"Task ID {task_id} not found."
        except Exception as e:
            return f"Error deleting task: {str(e)}"

    @mcp.tool(name=f"{TOOL_PREFIX}task_complete")
    async def task_complete(task_id: int) -> str:
        """Mark a task/subtask as 'completed'."""
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("UPDATE task SET status = 'completed' WHERE id = ?", (task_id,))
            affected = cur.rowcount
            conn.commit()
            conn.close()
            
            if affected > 0:
                return f"Task {task_id} marked as completed."
            return f"Task ID {task_id} not found."
        except Exception as e:
            return f"Error completing task: {str(e)}"


# ----------------- Read Operations -----------------

@mcp.tool(name=f"{TOOL_PREFIX}project_list")
async def project_list(status: str = "active") -> List[Any]:
    """List projects (default lists 'active' projects)."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, description, status, created_at FROM project WHERE status = ?", (status,))
        
        projects = []
        for row in cur:
            proj = format_row_to_dict(cur, row)
            proj['created_at'] = str(proj['created_at'])
            projects.append(proj)
        conn.close()
        
        if not projects:
            return [TextContent(type="text", text="No projects found.")]
            
        return [TextContent(type="text", text=json.dumps(projects, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error listing projects: {str(e)}")]

@mcp.tool(name=f"{TOOL_PREFIX}task_list")
async def task_list(project_id: int = 0, status: str = "") -> List[Any]:
    """
    List tasks and subtasks. 
    - project_id: Filter by a specific project ID (0 for all projects).
    - status: Filter by status (e.g., 'pending', 'completed'). Leaving empty returns all statuses.
    """
    try:
        query = "SELECT id, project_id, parent_task_id, title, description, status, priority, task_order, created_at, updated_at FROM task WHERE 1=1"
        params = []
        
        if project_id > 0:
            query += " AND project_id = ?"
            params.append(project_id)
        if status:
            query += " AND status = ?"
            params.append(status)
            
        query += " ORDER BY parent_task_id ASC, task_order ASC, priority DESC, created_at ASC"
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query, tuple(params))
        
        tasks = []
        for row in cur:
            task = format_row_to_dict(cur, row)
            task['created_at'] = str(task['created_at'])
            task['updated_at'] = str(task['updated_at'])
            tasks.append(task)
        conn.close()
        
        if not tasks:
            return [TextContent(type="text", text="No tasks found matching criteria.")]
            
        return [TextContent(type="text", text=json.dumps(tasks, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error listing tasks: {str(e)}")]

@mcp.tool(name=f"{TOOL_PREFIX}task_get_next")
async def task_get_next(project_id: int) -> List[Any]:
    """
    Get the next uncompleted task from a project.
    It prioritizes tasks with higher priority, then earlier task_order, then older tasks. 
    It returns a root task (parent_task_id IS NULL) or subtask that is 'pending' or 'in_progress'.
    """
    try:
        query = """
            SELECT id, project_id, parent_task_id, title, description, status, priority, task_order 
            FROM task 
            WHERE project_id = ? AND status != 'completed'
            ORDER BY priority DESC, task_order ASC, created_at ASC 
            LIMIT 1
        """
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(query, (project_id,))
        row = cur.fetchone()
        
        if not row:
            conn.close()
            return [TextContent(type="text", text=f"No uncompleted tasks found for project {project_id}.")]
            
        task = format_row_to_dict(cur, row)
        conn.close()
        
        return [TextContent(type="text", text=json.dumps(task, indent=2))]
    except Exception as e:
        return [TextContent(type="text", text=f"Error getting next task: {str(e)}")]


# --- Authentication Middleware ---
class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        api_key_header = request.headers.get("X-API-Key")
        auth_header = request.headers.get("Authorization")

        provided_key = None
        if api_key_header:
            provided_key = api_key_header
        elif auth_header and auth_header.startswith("Bearer "):
            provided_key = auth_header.split(" ", 1)[1]

        if provided_key != self.api_key:
            return JSONResponse({"detail": "Unauthorized - Invalid or missing API Key"}, status_code=401)

        return await call_next(request)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tasks MCP Server")
    parser.add_argument("--stdio", action="store_true", help="Run the MCP server in standard stdio mode")
    parser.add_argument("--mcp", action="store_true", help="Run the MCP server in HTTP/SSE mode (default)")
    parser.add_argument("--api-key", type=str, help="Enforce API key authentication in HTTP mode")
    parser.add_argument("--env-base", type=str, default="", help="Prefix for environment variables")
    parser.add_argument("--read-only", action="store_true", help="Disable write functionality")
    parser.add_argument("--tool-prefix", type=str, default="", help="Prefix for MCP tool")
    parser.add_argument("--mcp-name", type=str, default="Tasks", help="MCP name, default: Tasks")
    parser.add_argument("--db-type", type=str, default="sqlite", choices=["mariadb", "sqlite"], help="Database type to use (mariadb or sqlite)")
    parser.add_argument("--sqlite-db", type=str, default=".codify/task.sqlite", help="Path to sqlite database file")

    args = parser.parse_args()

    if ENV_PREFIX:
        actual_prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        print(f"Using environment variable prefix: '{actual_prefix}'", file=sys.stderr)

    print(f"Using database type: {DB_TYPE}", file=sys.stderr)
    if DB_TYPE == "sqlite":
        print(f"SQLite database path: {SQLITE_DB}", file=sys.stderr)

    if READ_ONLY:
        print("Server is running in READ-ONLY mode (write tools disabled).", file=sys.stderr)

    if args.stdio:
        print("Starting Tasks MCP Server in STDIO mode...", file=sys.stderr)
        mcp.run()
    else:
        print(f"Starting Tasks MCP Server in HTTP mode on port {PORT}...", file=sys.stderr)

        starlette_app = mcp.streamable_http_app()

        if args.api_key:
            print("API Key authentication is ENABLED.", file=sys.stderr)
            starlette_app.add_middleware(APIKeyMiddleware, api_key=args.api_key)

        starlette_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        uvicorn.run(starlette_app, host="127.0.0.1", port=PORT)