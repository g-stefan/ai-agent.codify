# MCP Memory (Lightweight Knowledge Graph)
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import json
import uuid
import base64
import shutil
import argparse
import urllib.request
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path

import uvicorn
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP, Image
from mcp.types import ContentBlock, TextContent, ImageContent

import mariadb

# --- Pre-parse --env-base and --read-only ---
# We use a separate parser that ignores unknown args to grab the env-base prefix early,
# because we need it to resolve our module-level configuration variables below.
pre_parser = argparse.ArgumentParser(add_help=False)
pre_parser.add_argument("--env-base", type=str, default="")
pre_parser.add_argument("--read-only", action="store_true")
pre_parser.add_argument("--tool-prefix", type=str, default="memory_")
pre_parser.add_argument("--media-marker", type=str, default="<__media__>")
pre_parser.add_argument("--mcp-name", type=str, default="Memory")
pre_args, _ = pre_parser.parse_known_args()

ENV_PREFIX = pre_args.env_base
READ_ONLY = pre_args.read_only
TOOL_PREFIX = pre_args.tool_prefix
MEDIA_MARKER = pre_args.media_marker
MCP_NAME = pre_args.mcp_name


def get_env_var(name: str, default: Any = None) -> Any:
    """Get an environment variable, optionally applying the env-base prefix."""
    if ENV_PREFIX:
        # Ensure there is exactly one underscore between prefix and name
        prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        env_key = f"{prefix}{name}"
    else:
        env_key = name
    return os.environ.get(env_key, default)


# Initialize the MCP Server
mcp = FastMCP(MCP_NAME, stateless_http=True, json_response=False)

# Configuration via Environment Variables (with fallbacks and prefix support)
PORT = int(get_env_var("PORT", 48101))
DB_HOST = get_env_var("DB_HOST", "127.0.0.1")
DB_PORT = int(get_env_var("DB_PORT", 3306))
DB_USER = get_env_var("DB_USER", "root")
DB_PASS = get_env_var("DB_PASS", "")
DB_NAME = get_env_var("DB_NAME", "memory")
DB_SEARCH_LIMIT = int(get_env_var("DB_SEARCH_LIMIT", 8))

LLAMA_EMBED_URL = get_env_var("LLAMA_EMBED_URL", "http://127.0.0.1:8080/embeddings")

MEMORY_DIR = get_env_var("MEMORY_DIR", "Memory")
os.makedirs(MEMORY_DIR, exist_ok=True)

WORKSPACE_DIR = get_env_var("WORKSPACE_DIR", "Workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

# --- Helper Functions ---


def get_safe_path(base_folder: str, user_path: str) -> Path:
    """
    Validates a path to ensure it cannot escape the specified base_folder
    using path traversal (e.g., '../').

    Args:
        base_folder (str): The root directory where files are allowed to be accessed.
        user_path (str): The file path provided by the user.

    Returns:
        Path: The resolved, safe target Path object.

    Raises:
        PermissionError: If a path traversal attempt is detected.
        IsADirectoryError: If the target path points to the base directory itself.
    """
    # 1. Get the absolute, normalized path of the base folder.
    base_dir = Path(base_folder).resolve()

    # 2. Combine the base folder with the user-provided path.
    target_path = (base_dir / user_path).resolve()

    # 3. Check if the resolved target path is still within the base directory.
    if not target_path.is_relative_to(base_dir):
        raise PermissionError(
            f"Security Error: Path traversal detected! '{user_path}' is outside the allowed directory."
        )

    # 4. Prevent referencing the base directory itself directly if not wanted.
    if target_path == base_dir:
        raise IsADirectoryError(
            "Security Error: Target path cannot be the base directory itself."
        )

    return base_folder + "/" + user_path


def read_file_content_and_type(
    filepath: str, binary: bool = False
) -> tuple[str, bool, str]:
    """Helper to read file content and determine if it should be treated as an image."""
    ext = os.path.splitext(filepath)[1].lower()
    is_image = ext in [".png", ".jpeg", ".jpg"]

    if is_image:
        imageFormat = "jpeg" if ext in [".jpeg", ".jpg"] else "png"
        if binary:
            with open(filepath, "rb") as f:
                data = f.read()
                return data, True, imageFormat

        with open(filepath, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
            return b64_data, True, imageFormat
    else:
        # Treat other files as text
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), False, ""


def get_embedding(text_or_image_url: str, is_image: bool = False) -> List[float]:
    """Fetch embedding vector for a given text or image from the Llama Server."""
    if is_image:
        # Structure for multimodal data containing an image
        payload = {
            "content": [
                {"prompt_string": MEDIA_MARKER, "multimodal_data": [text_or_image_url]}
            ]
        }
    else:
        # Standard text structure
        payload = {
            "content": [{"prompt_string": text_or_image_url, "multimodal_data": []}]
        }

    req = urllib.request.Request(
        LLAMA_EMBED_URL, data=json.dumps(payload).encode("utf-8"), method="POST"
    )
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode("utf-8"))

        # Match standard openai or direct list response
        if isinstance(result, dict) and "data" in result:
            return result["data"][0]["embedding"]
        elif isinstance(result, list):
            sorted_data = sorted(result, key=lambda x: x.get("index", 0))
            emb = sorted_data[0].get("embedding", [])
            # In case of token-level embeddings, grab the last vector
            if isinstance(emb, list) and len(emb) > 0 and isinstance(emb[0], list):
                return emb[-1]
            return emb

    raise ValueError("Unrecognized embedding response format from server.")


def get_db_connection():
    """Helper to get MariaDB connection, omitting password if empty."""
    kwargs = {"host": DB_HOST, "port": DB_PORT, "user": DB_USER, "database": DB_NAME}
    if DB_PASS:
        kwargs["password"] = DB_PASS
    return mariadb.connect(**kwargs)


def get_node_type_id(name: str):
    """Get node type by name"""
    if len(name) == 0:
        return 0
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM `node_type` WHERE name = ?", (name,))
            row = cur.fetchone()
            if row:
                if not (row[0] == 0):
                    return row[0]
            cur.execute("INSERT INTO `node_type` (name) VALUES (?)", (name,))
            cur.execute("SELECT LAST_INSERT_ID()")
            rowId = cur.fetchone()[0]
            conn.commit()
            return rowId
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        print(f"Error: Could not get node type: {e}", file=sys.stderr)


def get_node_type_name(id: int):
    """Get node type by id"""
    if id == 0:
        return 0
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM `node_type` WHERE id = ?", (id,))
            row = cur.fetchone()
            if row:
                return row[0]
            return ""
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        print(f"Error: Could not get node type: {e}", file=sys.stderr)


def get_node_category_id(name: str):
    """Get node category by name"""
    if len(name) == 0:
        return 0
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM `node_category` WHERE name = ?", (name,))
            row = cur.fetchone()
            if row:
                if not (row[0] == 0):
                    return row[0]
            cur.execute("INSERT INTO `node_category` (name) VALUES (?)", (name,))
            cur.execute("SELECT LAST_INSERT_ID()")
            rowId = cur.fetchone()[0]
            conn.commit()
            return rowId
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        print(f"Error: Could not get node category: {e}", file=sys.stderr)

def has_category(name: str):
    """Check if category exists by name"""
    if len(name) == 0:
        return 0
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM `node_category` WHERE name = ?", (name,))
            row = cur.fetchone()
            if row:
                if not (row[0] == 0):
                    return row[0]
            return 0
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        print(f"Error: Could not get node category: {e}", file=sys.stderr)


def get_node_category_name(id: int):
    """Get node category by id"""
    if id == 0:
        return 0
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM `node_category` WHERE id = ?", (id,))
            row = cur.fetchone()
            if row:
                return row[0]
            return ""
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        print(f"Error: Could not get node category: {e}", file=sys.stderr)


def get_node_category_list(node_id: int):
    """Get node category list by node_id"""
    results = []
    if node_id == 0:
        return results
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                        SELECT name FROM `node_category`
                        INNER JOIN `node_x_category` ON `node_category`.`id` = `node_x_category`.`category__id`
                        WHERE `node_x_category`.`node__id` = ?
                        """,
                (node_id,),
            )
            for row in cur:
                results.append({"name": row[0]})
            return results
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        print(f"Error: Could not get node category: {e}", file=sys.stderr)


def add_node_to_category(nodeId: int, category: str):
    if nodeId == 0:
        return 0
    categoryId = get_node_category_id(category)
    if categoryId == 0:
        return 0

    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            query = """
                INSERT INTO `node_x_category` (node__id, category__id) 
                VALUES (?, ?)
            """
            cur.execute(query, (nodeId, categoryId))
            cur.execute("SELECT LAST_INSERT_ID()")
            rowId = cur.fetchone()[0]
            conn.commit()
            return rowId
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        return 0


def remove_node_from_category(nodeId: int, category: str):
    if nodeId == 0:
        return
    categoryId = get_node_category_id(category)
    if categoryId == 0:
        return

    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            query = """
                DELETE FROM `node_x_category` WHERE node__id=? AND category__id=?                
            """
            cur.execute(query, (nodeId, categoryId))
            conn.commit()
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        return


def db_delete_node(nodeId: int):
    if nodeId == 0:
        return
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()

            cur.execute(
                f"""
                    SELECT document FROM `node` WHERE id=?                        
                """,
                (nodeId,),
            )
            row = cur.fetchone()
            if row:
                filepath = get_safe_path(MEMORY_DIR, row[0])
                if os.path.exists(filepath):
                    os.remove(filepath)

            query = """
                DELETE FROM `node` WHERE id=?
            """
            cur.execute(query, (nodeId,))
            query = """
                DELETE FROM `node_relation` WHERE source__node__id=?
            """
            cur.execute(query, (nodeId,))
            query = """
                DELETE FROM `node_relation` WHERE target__node__id=?
            """
            cur.execute(query, (nodeId,))
            query = """
                DELETE FROM `node_x_category` WHERE node__id=?
            """
            cur.execute(query, (nodeId,))
            conn.commit()
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        return


def save_embedding_to_db(
    description: str,
    nodeType: str,
    doc_name: str,
    embedding: List[float],
    is_image: bool,
):
    """Insert the document filename, its embedding, and creation date into MariaDB."""

    nodeTypeId = get_node_type_id(nodeType)

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        emb_str = json.dumps(embedding)
        # Using NOW() to automatically stamp the memory creation time based on the DB server
        query = f"INSERT INTO `node` (node_type__id, created_at, description, document, embedding) VALUES (?, NOW(), ?, ?, VEC_FromText(?))"
        cur.execute(query, (nodeTypeId, description, doc_name, emb_str))
        cur.execute("SELECT LAST_INSERT_ID()")
        rowId = cur.fetchone()[0]
        conn.commit()
        return rowId
    finally:
        if "conn" in locals() and conn.open:
            conn.close()


def search_db(
    nodeCategory: str,
    nodeType: str,
    embedding: List[float],
    limit: int = DB_SEARCH_LIMIT,
) -> List[Dict[str, Any]]:
    """Find top matching document filenames and creation dates using Vector Cosine Distance."""
    nodeTypeId = get_node_type_id(nodeType)
    nodeCategoryId = get_node_category_id(nodeCategory)

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        emb_str = json.dumps(embedding)
        # Only higher similarity (e.g., < 0.1 is roughly a 90% match),
        query = f"""
            SELECT id, node_type__id, created_at, description, document, VEC_DISTANCE_COSINE(embedding, VEC_FromText(?)) as distance
            FROM `node`
            ORDER BY distance ASC
            LIMIT ?
        """
        opt = (emb_str, limit)
        if nodeTypeId:
            query = f"""
                SELECT id, node_type__id, created_at, description, document, VEC_DISTANCE_COSINE(embedding, VEC_FromText(?)) as distance
                FROM `node` WHERE node_type__id = ?
                ORDER BY distance ASC
                LIMIT ?
            """
            opt = (emb_str, nodeTypeId, limit)
        if nodeCategoryId:
            query = f"""
                SELECT `node`.`id`, node_type__id, created_at, description, document, VEC_DISTANCE_COSINE(embedding, VEC_FromText(?)) as distance
                FROM `node` INNER JOIN `node_x_category` ON `node`.`id` = `node_x_category`.`node__id`
                WHERE `node_x_category`.`category__id` = ?
                ORDER BY distance ASC
                LIMIT ?
            """
            opt = (emb_str, nodeCategoryId, limit)
        if nodeTypeId and nodeCategoryId:
            query = f"""
                SELECT `node`.`id`, node_type__id, created_at, description, document, VEC_DISTANCE_COSINE(embedding, VEC_FromText(?)) as distance
                FROM `node` INNER JOIN `node_x_category` ON `node`.`id` = `node_x_category`.`node__id`
                WHERE node_type__id = ? AND `node_x_category`.`category__id` = ?
                ORDER BY distance ASC
                LIMIT ?
            """
            opt = (emb_str, nodeTypeId, nodeCategoryId, limit)

        cur.execute(query, opt)
        # Filter similarity (e.g., < 0.6 is roughly a 40% match),
        results = []
        for row in cur:
            if row[5] < 0.6:
                results.append(
                    {
                        "id": row[0],
                        "type_id": row[1],
                        "created_at": row[2],
                        "description": row[3],
                        "document": row[4],
                    }
                )
        return results
    finally:
        if "conn" in locals() and conn.open:
            conn.close()


def recall_by_embedding(
    nodeCategory: str, nodeType: str, emb: List[float], limit: int = DB_SEARCH_LIMIT
) -> List[Any]:
    # 1. Vector Search DB for top matches
    db_matches = search_db(nodeCategory, nodeType, emb, limit=limit)

    if not db_matches:
        return []

    # 2. Read matched documents
    documents = []
    for match in db_matches:
        fname = match["document"]
        filepath = get_safe_path(MEMORY_DIR, fname)

        if os.path.exists(filepath):
            nodeType = get_node_type_name(match["type_id"])
            documents.append(
                TextContent(
                    type="text",
                    text=(
                        '{"id":'
                        + str(match["id"])
                        + ',"description":"'
                        + str(match["description"])
                        + '"'
                        + ',"type":"'
                        + str(nodeType)
                        + '"}'
                    ),
                )
            )

            ext = os.path.splitext(filepath)[1].lower()
            is_image = ext in [".png", ".jpeg", ".jpg"]
            if is_image:
                content, is_image, imageFormat = read_file_content_and_type(
                    filepath, True
                )
                b64_data = base64.b64encode(content).decode("utf-8")
                documents.append(
                    ImageContent(
                        type="image",
                        data=b64_data,
                        mimeType=f"image/{imageFormat.lower()}",
                    )
                )
            else:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    documents.append(TextContent(type="text", text=content))

    return documents


def search_db_by_id(node_id: int) -> List[Dict[str, Any]]:
    """Get node by id"""

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        query = f"""
            SELECT id, node_type__id, created_at, description, document
            FROM `node`
            WHERE id = ?            
        """

        cur.execute(query, (node_id,))
        results = []
        for row in cur:
            results.append(
                {
                    "id": row[0],
                    "type_id": row[1],
                    "created_at": row[2],
                    "description": row[3],
                    "document": row[4],
                }
            )
        return results
    finally:
        if "conn" in locals() and conn.open:
            conn.close()


def recall_by_id(node_id: int) -> List[Any]:
    # 1. Vector Search DB for top matches
    db_matches = search_db_by_id(node_id)

    if not db_matches:
        return []

    # 2. Read matched documents
    documents = []
    for match in db_matches:
        fname = match["document"]
        filepath = get_safe_path(MEMORY_DIR, fname)

        if os.path.exists(filepath):
            nodeType = get_node_type_name(match["type_id"])
            documents.append(
                TextContent(
                    type="text",
                    text=(
                        '{"id":'
                        + str(match["id"])
                        + ',"description":"'
                        + str(match["description"])
                        + '"'
                        + ',"type":"'
                        + str(nodeType)
                        + '"}'
                    ),
                )
            )

            ext = os.path.splitext(filepath)[1].lower()
            is_image = ext in [".png", ".jpeg", ".jpg"]
            if is_image:
                content, is_image, imageFormat = read_file_content_and_type(
                    filepath, True
                )
                b64_data = base64.b64encode(content).decode("utf-8")
                documents.append(
                    ImageContent(
                        type="image",
                        data=b64_data,
                        mimeType=f"image/{imageFormat.lower()}",
                    )
                )
            else:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    documents.append(TextContent(type="text", text=content))

    return documents


# --- MCP Tools ---

# Only register write functionality if not in read-only mode
if not READ_ONLY:

    @mcp.tool(name=f"{TOOL_PREFIX}remember")
    async def remember(
        info: str, description: str = "", type: str = "", category: str = ""
    ) -> str:
        """
        Use this tool to save new text information, facts, concepts, or knowledge into the long-term memory.

        Parameters:
        - info (str): The actual text content, fact, or data you want the system to remember.
        - description (str, optional): A short description about the data, a title.
        - type (str, optional): A tag to define the kind of information (e.g., 'person', 'concept', 'meeting_note').
        - category (str, optional): A tag to group related memories together (e.g., 'project_x', 'history').

        Returns:
        A confirmation string containing the newly generated integer `node_id`. Always take note of this `node_id`
        so you can link it to other memories later using the `link_nodes` tool.
        """
        try:
            now = datetime.now()
            date_folder = now.strftime("%Y-%m-%d")
            hour_folder = now.strftime("%H")
            doc_id = str(uuid.uuid4())
            # The relative filename used in DB e.g. "2026-04-28/01/UUID.txt"
            rel_filename = f"{date_folder}/{hour_folder}/{doc_id}.txt"
            # The absolute path on disk
            filepath = os.path.join(
                MEMORY_DIR, date_folder, hour_folder, f"{doc_id}.txt"
            )
            # Ensure the nested directories exist
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # 1. Save content to Workspace Folder (Memory Directory)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(info)

            # 2. Fetch Embeddings
            emb = get_embedding(info)

            # 3. Save to MariaDB
            nodeId = save_embedding_to_db(description, type, rel_filename, emb, False)
            add_node_to_category(nodeId, category)

            return f"Memory successfully saved, node_id: {nodeId}."
        except Exception as e:
            return f"Error saving memory: {str(e)}"

    @mcp.tool(name=f"{TOOL_PREFIX}remember_file")
    async def remember_file(
        filename: str, description: str = "", type: str = "", category: str = ""
    ) -> str:
        """
        Use this tool to save a file (like an image or a text document) that ALREADY EXISTS in the Workspace into the long-term memory.

        Parameters:
        - filename (str): The exact name of the file currently sitting in the Workspace (e.g., 'diagram.png', 'notes.txt').
        - type (str, optional): The type or format of the file's content (e.g., 'diagram', 'document').
        - category (str, optional): A tag to group this file with other related memories.

        Returns:
        A confirmation string containing the newly generated integer `node_id` for the saved file. Use this ID to create relations.
        """
        try:
            original_filepath = get_safe_path(WORKSPACE_DIR, filename)
            if not os.path.exists(original_filepath):
                return f"Error: File '{filename}' not found in Workspace."

            print("remember file #1: " + str(filename))

            # Generate date and hour folder strings
            now = datetime.now()
            date_folder = now.strftime("%Y-%m-%d")
            hour_folder = now.strftime("%H")

            # Generate new GUID-based filename
            doc_id = str(uuid.uuid4())
            _, ext = os.path.splitext(filename)

            # The relative filename used in DB
            rel_filename = f"{date_folder}/{hour_folder}/{doc_id}{ext}"

            # The absolute path on disk
            new_filepath = os.path.join(
                MEMORY_DIR, date_folder, hour_folder, f"{doc_id}{ext}"
            )

            # Ensure the nested directories exist
            os.makedirs(os.path.dirname(new_filepath), exist_ok=True)

            print("remember file #2: " + str(rel_filename))

            # Read content and fetch embeddings
            content, is_image, imageFormat = read_file_content_and_type(
                original_filepath
            )

            print("remember file #3: " + str(is_image))

            emb = get_embedding(content, is_image=is_image)

            print("remember file #4")

            # Copy the file to the memory directory with the new name
            shutil.copy2(original_filepath, new_filepath)

            print("remember file #5")

            # Save to MariaDB with the new filename
            nodeId = save_embedding_to_db(
                description, type, rel_filename, emb, is_image
            )
            add_node_to_category(nodeId, category)

            print("remember file #6")

            return f"Memory successfully saved, node_id: {nodeId}."
        except Exception as e:
            return f"Error saving file to memory: {str(e)}"

    @mcp.tool(name=f"{TOOL_PREFIX}create_relationship")
    async def create_relationship(source_id: int, target_id: int, relation: str) -> str:
        """
        Use this tool to create a semantic relationship between two existing memory nodes in the knowledge graph.

        Parameters:
        - source_id (int): The integer ID of the origin node (obtained from a previous 'remember' or 'recall' action).
        - target_id (int): The integer ID of the destination node to link to.
        - relation (str): A short string describing exactly how the source relates to the target
          (e.g., 'is_a', 'depends_on', 'authored_by', 'causes', 'relates_to').

        Returns:
        A success message confirming the link was established.
        """
        try:
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                query = """
                    INSERT INTO `node_relation` (source__node__id, target__node__id, relation) 
                    VALUES (?, ?, ?)
                """
                cur.execute(query, (source_id, target_id, relation))
                conn.commit()
                return f"Successfully linked node_id {source_id} to node_id {target_id} with relation '{relation}'."
            finally:
                if "conn" in locals() and conn.open:
                    conn.close()
        except Exception as e:
            return f"Error linking nodes: {str(e)}"
        
    @mcp.tool(name=f"{TOOL_PREFIX}delete_relationship")
    async def delete_relationship(source_id: int, target_id: int) -> str:
        """
        Use this tool to delete a semantic relationship between two existing memory nodes in the knowledge graph.

        Parameters:
        - source_id (int): The integer ID of the origin node.
        - target_id (int): The integer ID of the destination node.
        
        """
        try:
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                query = """
                    DELETE FROM `node_relation` WHERE source__node__id=? AND target__node__id=?                    
                """
                cur.execute(query, (source_id, target_id, ))
                conn.commit()
                return f"Successfully deleted relation between node_id {source_id} and node_id {target_id}."
            finally:
                if "conn" in locals() and conn.open:
                    conn.close()
        except Exception as e:
            return f"Error delete relation: {str(e)}"

    @mcp.tool(name=f"{TOOL_PREFIX}link_node_to_category")
    async def link_node_to_category(node_id: int, category: str) -> str:
        """
        Use this tool to add an existing memory node to a specific category. This makes it easier to filter and find later.

        Parameters:
        - node_id (int): The integer ID of the memory node.
        - category (str): The string name of the category to assign (e.g., 'science', 'urgent', 'personal').
        """
        rowId = add_node_to_category(node_id, category)
        if rowId:
            return f"Successfully linked node {node_id} to category '{category}'."
        return f"Error linking node."

    @mcp.tool(name=f"{TOOL_PREFIX}remove_node_from_category")
    async def remove_node_from_category(node_id: int, category: str) -> str:
        """
        Use this tool to remove an existing memory node from a specific category.

        Parameters:
        - node_id (int): The integer ID of the memory node.
        - category (str): The string name of the category you want to remove the node from.
        """
        remove_node_from_category(node_id, category)
        return f"Removed"

    @mcp.tool(name=f"{TOOL_PREFIX}delete_node")
    async def delete_node(node_id: int) -> str:
        """
        Use this tool to delete an existing memory node.

        Parameters:
        - node_id (int): The integer ID of the memory node.
        """

        db_delete_node(node_id)

        return f"Deleted"


@mcp.tool(name=f"{TOOL_PREFIX}recall")
async def recall(
    text_or_image_description: str,
    type: str = "",
    category: str = "",
    memories_limit: int = 8,
) -> List[Any]:
    """
    Use this tool to search the long-term memory for information.

    Parameters:
    - text_or_image_description (str): The search query, question, or a description of the image you are looking for.
    - type (str, optional): Filter the search results to only return nodes of a specific type (e.g., 'concept').
    - category (str, optional): Filter the search results to only return nodes within a specific category.
    - memories_limit (int, optional): The maximum number of relevant memories to return. Defaults to 8.

    Returns:
    A list of matching memories. Each memory will include its integer `node_id` and the actual text or image content.
    You can use the returned `node_id`s with the `get_node_relations` tool to explore connected information.
    """
    try:
        emb = get_embedding(text_or_image_description)
        documents = recall_by_embedding(category, type, emb, memories_limit)
        if not documents:
            return [
                TextContent(
                    type="text",
                    text="No memory found",
                )
            ]

        return documents
    except Exception as e:
        return [TextContent(type="text", text=f"Error recalling memory: {str(e)}")]


@mcp.tool(name=f"{TOOL_PREFIX}recall_by_file")
async def recall_by_file(
    filename: str, type: str = "", category: str = "", memories_limit: int = 8
) -> List[Any]:
    """
    Use this tool to search the memory by comparing it against the contents of an existing file in the Workspace.

    Parameters:
    - filename (str): The name of the file currently in the Workspace whose content you want to use as the search query.
    - type (str, optional): Filter the search results to a specific node type.
    - category (str, optional): Filter the search results to a specific category.
    - memories_limit (int, optional): The maximum number of relevant memories to return. Defaults to 8.

    Returns:
    A list of memories that are semantically similar to the file's text or image content.
    """
    try:
        filepath = get_safe_path(WORKSPACE_DIR, filename)
        if not os.path.exists(filepath):
            return [f"Error: File '{filename}' not found in Workspace."]

        content, is_image, imageFormat = read_file_content_and_type(filepath)

        # Get embedding for the file
        emb = get_embedding(content, is_image=is_image)

        documents = recall_by_embedding(category, type, emb, memories_limit)
        if not documents:
            return [
                TextContent(
                    type="text",
                    text="No memory found",
                )
            ]
        return documents
    except Exception as e:
        return [f"Error recalling by file: {str(e)}"]


@mcp.tool(name=f"{TOOL_PREFIX}recall_by_node_id")
async def recall_by_node_id(node_id: int) -> List[Any]:
    """
    Use this tool to get the content of a node from memory.

    Parameters:
    - node_id (int): The requested node_id.

    Returns:
    The memory stored on node_id.
    """
    try:
        documents = recall_by_id(node_id)
        if not documents:
            return [
                TextContent(
                    type="text",
                    text="No memory found",
                )
            ]
        return documents
    except Exception as e:
        return [f"Error recalling by file: {str(e)}"]


@mcp.tool(name=f"{TOOL_PREFIX}get_node_relations")
async def get_node_relations(node_id: int) -> List[Any]:
    """
    Use this tool to explore the knowledge graph by finding all other memories connected to a specific memory node.

    Parameters:
    - node_id (int): The integer ID of the memory node you want to investigate.

    Returns:
    A list of all incoming and outgoing links for that node. The results include the 'direction' (incoming/outgoing),
    the 'relation' type (e.g., 'depends_on'), and the 'related_node_id'.
    If you want to read the content of the connected nodes, use the `recall` tool to search for those specific related node IDs.
    """
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            query = """
                SELECT 'outgoing' as direction, target__node__id as related_node_id, relation
                FROM `node_relation` WHERE source__node__id = ?
                UNION ALL
                SELECT 'incoming' as direction, source__node__id as related_node_id, relation
                FROM `node_relation` WHERE target__node__id = ?
            """
            cur.execute(query, (node_id, node_id))

            results = []
            for row in cur:
                results.append(
                    '{"direction":"'
                    + str(row[0])
                    + '","relation":"'
                    + str(row[2])
                    + '","node_id":'
                    + str(row[1])
                    + "}"
                )

            if not results:
                return [
                    TextContent(
                        type="text",
                        text=f"No relations found for memory node_id: {node_id}",
                    )
                ]

            header = f"Relations for memory node_id: {node_id}\n"
            return [TextContent(type="text", text=header + "\n".join(results))]
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        return [
            TextContent(type="text", text=f"Error getting node relations: {str(e)}")
        ]


@mcp.tool(name=f"{TOOL_PREFIX}get_node_category")
async def get_node_category(node_id: int) -> List[Any]:
    """
    Use this tool to get categories assigned to a specific memory node.

    Parameters:
    - node_id (int): The integer ID of the memory node you want to investigate.

    Returns:
    A list of all categories that this node are part of.
    """
    results = get_node_category_list(node_id)
    if not results:
        return [
            TextContent(
                type="text",
                text=f"No category found for memory node_id: {node_id}",
            )
        ]
    header = f"Categories for memory node_id: {node_id}\n"
    return [TextContent(type="text", text=header + ", ".join(results))]

@mcp.tool(name=f"{TOOL_PREFIX}category_exists")
async def category_exists(name: str) -> str:
    """
    Use this tool to check if a category with specified name exists.
    """

    if has_category(name) == 0:
        return f"Category with name '{name}' does not exists."
            
    return f"Category with name '{name}' found."

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
    # Main argument parser includes all arguments, including the --env-base we already processed
    parser = argparse.ArgumentParser(description="Memory MCP Server")
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
        default="memory_",
        help="Prefix for MCP tool",
    )
    parser.add_argument(
        "--media-marker",
        type=str,
        default="<__media__>",
        help="Media marker for image embeddings",
    )
    parser.add_argument(
        "--mcp-name",
        type=str,
        default="Memory",
        help="MCP name, default: Memory",
    )

    args = parser.parse_args()

    # Note: When using stdio mode, standard out must be clean for JSON-RPC messages.
    # Therefore, all initialization logs are routed to sys.stderr.
    if ENV_PREFIX:
        actual_prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        print(
            f"Using environment variable prefix: '{actual_prefix}' (e.g., expecting {actual_prefix}PORT)",
            file=sys.stderr,
        )

    if READ_ONLY:
        print(
            "Server is running in READ-ONLY mode (write tools disabled).",
            file=sys.stderr,
        )

    if args.stdio:
        print("Starting Memory MCP Server in STDIO mode...", file=sys.stderr)
        mcp.run()
    else:
        # Default mode (HTTP)
        print(
            f"Starting Memory MCP Server in HTTP mode on port {PORT}...",
            file=sys.stderr,
        )

        starlette_app = mcp.streamable_http_app()

        # 1. Add API Key Middleware if the command line argument is provided
        if args.api_key:
            print("API Key authentication is ENABLED.", file=sys.stderr)
            starlette_app.add_middleware(APIKeyMiddleware, api_key=args.api_key)

        # 2. Add CORS Middleware (Added last so it wraps the app first, handling OPTIONS directly)
        starlette_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        uvicorn.run(starlette_app, host="127.0.0.1", port=PORT)
