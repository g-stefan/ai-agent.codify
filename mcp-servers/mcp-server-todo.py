# MCP ToDo
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import json
import argparse
import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime

import uvicorn
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

try:
    import mariadb
except ImportError:
    mariadb = None

# --- Pre-parse --env-base and --read-only ---
pre_parser = argparse.ArgumentParser(add_help=False)
pre_parser.add_argument("--env-base", type=str, default="")
pre_parser.add_argument("--read-only", action="store_true")
pre_parser.add_argument("--tool-prefix", type=str, default="todo_")
pre_parser.add_argument("--mcp-name", type=str, default="ToDo")
pre_parser.add_argument("--db-type", type=str, default="sqlite", choices=["sqlite", "mariadb"])
pre_parser.add_argument("--sqlite-db-path", type=str, default=".codify/todo.sqlite")
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
PORT = int(get_env_var("PORT", 48102))
DB_TYPE = get_env_var("DB_TYPE", pre_args.db_type).lower()
SQLITE_DB_PATH = get_env_var("SQLITE_DB_PATH", pre_args.sqlite_db_path)

# MariaDB specific config
DB_HOST = get_env_var("DB_HOST", "127.0.0.1")
DB_PORT = int(get_env_var("DB_PORT", 3306))
DB_USER = get_env_var("DB_USER", "root")
DB_PASS = get_env_var("DB_PASS", "")
DB_NAME = get_env_var("DB_NAME", "todo_db")

# --- Helper Functions ---

def get_db_connection():
    """Helper to get DB connection based on configured DB_TYPE."""
    if DB_TYPE == "sqlite":
        db_dir = os.path.dirname(SQLITE_DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        # timeout is crucial to prevent "database is locked" errors in concurrent environments
        conn = sqlite3.connect(SQLITE_DB_PATH, timeout=15.0)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn
    elif DB_TYPE == "mariadb":
        if mariadb is None:
            raise RuntimeError("The 'mariadb' module is not installed. Install it or use '--db-type sqlite'")
        kwargs = {"host": DB_HOST, "port": DB_PORT, "user": DB_USER, "database": DB_NAME}
        if DB_PASS:
            kwargs["password"] = DB_PASS
        return mariadb.connect(**kwargs)
    else:
        raise ValueError(f"Unsupported DB_TYPE: {DB_TYPE}")

def init_sqlite_db():
    """Ensure the SQLite schema exists on startup if using SQLite."""
    if DB_TYPE != "sqlite":
        return
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Create Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS `todos` (
                `id` INTEGER PRIMARY KEY AUTOINCREMENT,
                `title` VARCHAR(255) NOT NULL,
                `description` TEXT,
                `is_completed` TINYINT(1) DEFAULT 0,
                `priority` VARCHAR(10) DEFAULT 'medium',
                `due_date` DATE NULL,
                `category` VARCHAR(100) DEFAULT NULL,
                `parent_id` INT DEFAULT NULL,
                `task_order` INT DEFAULT 0,
                `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT `fk_parent` FOREIGN KEY (`parent_id`) REFERENCES `todos`(`id`) ON DELETE CASCADE
            )
        """)
        # Create auto-update trigger for updated_at
        cur.execute("""
            CREATE TRIGGER IF NOT EXISTS update_todos_updated_at
            AFTER UPDATE ON todos
            FOR EACH ROW
            BEGIN
                UPDATE todos SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
            END;
        """)
        # Create Indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_title ON todos(title)",
            "CREATE INDEX IF NOT EXISTS idx_category ON todos(category)",
            "CREATE INDEX IF NOT EXISTS idx_parent_id ON todos(parent_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_order ON todos(task_order)",
            "CREATE INDEX IF NOT EXISTS idx_created_at ON todos(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_is_completed ON todos(is_completed)",
            "CREATE INDEX IF NOT EXISTS idx_due_date ON todos(due_date)"
        ]
        for idx in indexes:
            cur.execute(idx)
        
        conn.commit()
    finally:
        if "conn" in locals():
            conn.close()

# Initialize schema instantly if using sqlite
init_sqlite_db()

def format_todo(row: tuple) -> Dict[str, Any]:
    """Format a database row into a dictionary."""
    return {
        "id": row[0],
        "title": row[1],
        "description": row[2],
        "is_completed": bool(row[3]),
        "priority": row[4],
        "due_date": str(row[5]) if row[5] else None,
        "category": row[6],
        "parent_id": row[7],
        "task_order": row[8],
        "created_at": str(row[9]),
        "updated_at": str(row[10])
    }

# --- MCP Tools ---

# --- WRITE OPERATIONS (Disabled if READ_ONLY) ---
if not READ_ONLY:

    @mcp.tool(name=f"{TOOL_PREFIX}create")
    async def create_todo(
        title: str, 
        description: str = "", 
        priority: str = "medium", 
        due_date: str = None,
        category: str = None,
        parent_id: int = None,
        task_order: int = 0
    ) -> str:
        """
        Create a new todo item.

        Parameters:
        - title (str): The title or main task of the todo.
        - description (str, optional): Additional details about the task.
        - priority (str, optional): Priority level ('low', 'medium', 'high'). Defaults to 'medium'.
        - due_date (str, optional): Due date in format YYYY-MM-DD.
        - category (str, optional): A category to group tasks together.
        - parent_id (int, optional): ID of the parent todo (if this is a subtask).
        - task_order (int, optional): Numerical order for custom sorting. Defaults to 0.
        """
        if priority not in ['low', 'medium', 'high']:
            return "Error: priority must be 'low', 'medium', or 'high'."

        try:
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                query = """
                    INSERT INTO `todos` (title, description, priority, due_date, category, parent_id, task_order) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """
                cur.execute(query, (title, description, priority, due_date, category, parent_id, task_order))
                
                if DB_TYPE == "sqlite":
                    todo_id = cur.lastrowid
                else:
                    cur.execute("SELECT LAST_INSERT_ID()")
                    todo_id = cur.fetchone()[0]
                
                conn.commit()
                return f"Successfully created todo with id: {todo_id}."
            finally:
                if "conn" in locals():
                    conn.close()
        except Exception as e:
            return f"Error creating todo: {str(e)}"

    @mcp.tool(name=f"{TOOL_PREFIX}update")
    async def update_todo(
        todo_id: int, 
        title: str = None, 
        description: str = None, 
        priority: str = None, 
        due_date: str = None,
        category: str = None,
        parent_id: int = None,
        task_order: int = None
    ) -> str:
        """
        Update an existing todo's details. Only provided fields will be updated.

        Parameters:
        - todo_id (int): The ID of the todo to update.
        - title (str, optional): New title.
        - description (str, optional): New description.
        - priority (str, optional): New priority ('low', 'medium', 'high').
        - due_date (str, optional): New due date (YYYY-MM-DD). Use 'NULL' to clear it.
        - category (str, optional): New category. Use 'NULL' to clear it.
        - parent_id (int, optional): New parent ID. Use -1 to detach and make it a root task.
        - task_order (int, optional): New order number for custom sorting.
        """
        fields = []
        params = []

        if title is not None:
            fields.append("title = ?")
            params.append(title)
        if description is not None:
            fields.append("description = ?")
            params.append(description)
        if priority is not None:
            if priority not in ['low', 'medium', 'high']:
                return "Error: priority must be 'low', 'medium', or 'high'."
            fields.append("priority = ?")
            params.append(priority)
        if due_date is not None:
            fields.append("due_date = ?")
            params.append(None if due_date.upper() == 'NULL' else due_date)
        if category is not None:
            fields.append("category = ?")
            params.append(None if category.upper() == 'NULL' else category)
        if parent_id is not None:
            fields.append("parent_id = ?")
            params.append(None if parent_id == -1 else parent_id)
        if task_order is not None:
            fields.append("task_order = ?")
            params.append(task_order)

        if not fields:
            return "No fields provided to update."

        params.append(todo_id)

        try:
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                query = f"UPDATE `todos` SET {', '.join(fields)} WHERE id = ?"
                cur.execute(query, tuple(params))
                if cur.rowcount == 0:
                    return f"No todo found with id {todo_id}."
                conn.commit()
                return f"Successfully updated todo {todo_id}."
            finally:
                if "conn" in locals():
                    conn.close()
        except Exception as e:
            return f"Error updating todo: {str(e)}"

    @mcp.tool(name=f"{TOOL_PREFIX}complete")
    async def complete_todo(todo_id: int) -> str:
        """
        Mark a todo as completed.

        Parameters:
        - todo_id (int): The ID of the todo.
        """
        try:
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                query = "UPDATE `todos` SET is_completed = 1 WHERE id = ?"
                cur.execute(query, (todo_id,))
                if cur.rowcount == 0:
                    return f"No todo found with id {todo_id}."
                conn.commit()
                return f"Successfully marked todo {todo_id} as completed."
            finally:
                if "conn" in locals():
                    conn.close()
        except Exception as e:
            return f"Error completing todo: {str(e)}"

    @mcp.tool(name=f"{TOOL_PREFIX}delete")
    async def delete_todo(todo_id: int) -> str:
        """
        Delete a todo permanently.

        Parameters:
        - todo_id (int): The ID of the todo to delete.
        """
        try:
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                query = "DELETE FROM `todos` WHERE id = ?"
                cur.execute(query, (todo_id,))
                if cur.rowcount == 0:
                    return f"No todo found with id {todo_id}."
                conn.commit()
                return f"Successfully deleted todo {todo_id}."
            finally:
                if "conn" in locals():
                    conn.close()
        except Exception as e:
            return f"Error deleting todo: {str(e)}"


# --- READ OPERATIONS (Always Available) ---

@mcp.tool(name=f"{TOOL_PREFIX}list")
async def list_todos(limit: int = 50, offset: int = 0, category: str = None, parent_id: int = None) -> List[Any]:
    """
    List all todos, sorted by oldest first (order added).

    Parameters:
    - limit (int, optional): Maximum number of results to return.
    - offset (int, optional): Number of results to skip.
    - category (str, optional): Filter by category.
    - parent_id (int, optional): Filter by parent_id (e.g., to get subtasks). Use -1 to get only root tasks.
    """
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            
            where_clauses = []
            params = []
            
            if category is not None:
                where_clauses.append("category = ?")
                params.append(category)
            
            if parent_id is not None:
                if parent_id == -1:
                    where_clauses.append("parent_id IS NULL")
                else:
                    where_clauses.append("parent_id = ?")
                    params.append(parent_id)
                    
            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
            params.extend([limit, offset])

            query = f"""
                SELECT id, title, description, is_completed, priority, due_date, category, parent_id, task_order, created_at, updated_at 
                FROM `todos` {where_sql} ORDER BY task_order ASC, created_at ASC LIMIT ? OFFSET ?
            """
            cur.execute(query, tuple(params))
            results = [format_todo(row) for row in cur]
            
            if not results:
                return [TextContent(type="text", text="No todos found.")]
            return [TextContent(type="text", text=json.dumps(results, indent=2))]
        finally:
            if "conn" in locals():
                conn.close()
    except Exception as e:
        return [TextContent(type="text", text=f"Error listing todos: {str(e)}")]

@mcp.tool(name=f"{TOOL_PREFIX}list_active")
async def list_active_todos(limit: int = 50, offset: int = 0, category: str = None, parent_id: int = None) -> List[Any]:
    """
    List all non-completed (active) todos, sorted by highest priority and then oldest first.
    """
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            
            where_clauses = ["is_completed = 0"]
            params = []
            
            if category is not None:
                where_clauses.append("category = ?")
                params.append(category)
            
            if parent_id is not None:
                if parent_id == -1:
                    where_clauses.append("parent_id IS NULL")
                else:
                    where_clauses.append("parent_id = ?")
                    params.append(parent_id)
                    
            where_sql = "WHERE " + " AND ".join(where_clauses)
            params.extend([limit, offset])

            query = f"""
                SELECT id, title, description, is_completed, priority, due_date, category, parent_id, task_order, created_at, updated_at 
                FROM `todos` 
                {where_sql} 
                ORDER BY 
                    task_order ASC,
                    CASE priority 
                        WHEN 'high' THEN 1 
                        WHEN 'medium' THEN 2 
                        WHEN 'low' THEN 3 
                        ELSE 4 
                    END, 
                    due_date ASC, 
                    created_at ASC 
                LIMIT ? OFFSET ?
            """
            cur.execute(query, tuple(params))
            results = [format_todo(row) for row in cur]
            
            if not results:
                return [TextContent(type="text", text="No active todos found.")]
            return [TextContent(type="text", text=json.dumps(results, indent=2))]
        finally:
            if "conn" in locals():
                conn.close()
    except Exception as e:
        return [TextContent(type="text", text=f"Error listing active todos: {str(e)}")]

@mcp.tool(name=f"{TOOL_PREFIX}get")
async def get_todo(todo_id: int) -> List[Any]:
    """
    Get a specific todo by its integer ID.
    """
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            query = """
                SELECT id, title, description, is_completed, priority, due_date, category, parent_id, task_order, created_at, updated_at 
                FROM `todos` WHERE id = ?
            """
            cur.execute(query, (todo_id,))
            row = cur.fetchone()
            
            if not row:
                return [TextContent(type="text", text=f"Todo {todo_id} not found.")]
            return [TextContent(type="text", text=json.dumps(format_todo(row), indent=2))]
        finally:
            if "conn" in locals():
                conn.close()
    except Exception as e:
        return [TextContent(type="text", text=f"Error getting todo: {str(e)}")]

@mcp.tool(name=f"{TOOL_PREFIX}search_by_title")
async def search_todos_by_title(title_query: str) -> List[Any]:
    """
    Search todos by title using a case-insensitive partial match.
    """
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            query = """
                SELECT id, title, description, is_completed, priority, due_date, category, parent_id, task_order, created_at, updated_at 
                FROM `todos` WHERE title LIKE ? ORDER BY task_order ASC, created_at ASC
            """
            search_pattern = f"%{title_query}%"
            cur.execute(query, (search_pattern,))
            results = [format_todo(row) for row in cur]
            
            if not results:
                return [TextContent(type="text", text=f"No todos found matching '{title_query}'.")]
            return [TextContent(type="text", text=json.dumps(results, indent=2))]
        finally:
            if "conn" in locals():
                conn.close()
    except Exception as e:
        return [TextContent(type="text", text=f"Error searching todos: {str(e)}")]

@mcp.tool(name=f"{TOOL_PREFIX}search_by_date")
async def search_todos_by_date(date: str) -> List[Any]:
    """
    Search todos by exact creation date.

    Parameters:
    - date (str): The creation date to search for in YYYY-MM-DD format.
    """
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            query = """
                SELECT id, title, description, is_completed, priority, due_date, category, parent_id, task_order, created_at, updated_at 
                FROM `todos` WHERE DATE(created_at) = ? ORDER BY task_order ASC, created_at ASC
            """
            cur.execute(query, (date,))
            results = [format_todo(row) for row in cur]
            
            if not results:
                return [TextContent(type="text", text=f"No todos found created on {date}.")]
            return [TextContent(type="text", text=json.dumps(results, indent=2))]
        finally:
            if "conn" in locals():
                conn.close()
    except Exception as e:
        return [TextContent(type="text", text=f"Error searching by date: {str(e)}")]

# --- Authentication Middleware ---

class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce API key authentication on HTTP endpoints."""

    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request, call_next):
        # Allow CORS preflight requests to pass through without authentication
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check both X-API-Key and Authorization Bearer token headers
        api_key_header = request.headers.get("X-API-Key")
        auth_header = request.headers.get("Authorization")

        provided_key = None
        if api_key_header:
            provided_key = api_key_header
        elif auth_header and auth_header.startswith("Bearer "):
            provided_key = auth_header.split(" ", 1)[1]

        if provided_key != self.api_key:
            return JSONResponse(
                {"detail": "Unauthorized - Invalid or missing API Key"}, status_code=401
            )

        return await call_next(request)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ToDo MCP Server")
    parser.add_argument(
        "--stdio", action="store_true", help="Run the MCP server in standard stdio mode"
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Run the MCP server in HTTP/SSE mode (default)",
    )
    parser.add_argument(
        "--api-key", type=str, help="Enforce API key authentication in HTTP mode"
    )
    parser.add_argument(
        "--env-base",
        type=str,
        default="",
        help="Prefix for environment variables (e.g. 'PREFIX' checks for 'PREFIX_VARIABLE')",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Disable write functionality (only recall functions will be active)",
    )
    parser.add_argument(
        "--tool-prefix",
        type=str,
        default="todo_",
        help="Prefix for MCP tool",
    )
    parser.add_argument(
        "--mcp-name",
        type=str,
        default="ToDoServer",
        help="MCP name, default: ToDoServer",
    )
    parser.add_argument(
        "--db-type",
        type=str,
        default="sqlite",
        choices=["sqlite", "mariadb"],
        help="Database backend to use (default: sqlite)",
    )
    parser.add_argument(
        "--sqlite-db-path",
        type=str,
        default=".codify/todo.sqlite",
        help="Path to SQLite database file. Created automatically.",
    )

    args = parser.parse_args()

    if ENV_PREFIX:
        actual_prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        print(
            f"Using environment variable prefix: '{actual_prefix}' (e.g., expecting {actual_prefix}PORT)",
            file=sys.stderr,
        )

    print(f"Server is running with database backend: {DB_TYPE.upper()}", file=sys.stderr)
    if DB_TYPE == "sqlite":
        print(f"SQLite DB Path: {os.path.abspath(SQLITE_DB_PATH)}", file=sys.stderr)

    if READ_ONLY:
        print(
            "Server is running in READ-ONLY mode (write tools disabled).",
            file=sys.stderr,
        )

    if args.stdio:
        print("Starting ToDo MCP Server in STDIO mode...", file=sys.stderr)
        mcp.run()
    else:
        # Default mode (HTTP)
        print(
            f"Starting ToDo MCP Server in HTTP mode on port {PORT}...",
            file=sys.stderr,
        )

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