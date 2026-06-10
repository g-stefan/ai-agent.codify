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
from typing import List, Dict, Any, Optional
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
        prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        env_key = f"{prefix}{name}"
    else:
        env_key = name
    return os.environ.get(env_key, default)


# Initialize the MCP Server
mcp = FastMCP(MCP_NAME, stateless_http=True, json_response=False)

# Configuration via Environment Variables
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
    """Validates a path to ensure it cannot escape the specified base_folder."""
    base_dir = Path(base_folder).resolve()
    target_path = (base_dir / user_path).resolve()
    if not target_path.is_relative_to(base_dir):
        raise PermissionError(f"Security Error: Path traversal detected! '{user_path}' is outside the allowed directory.")
    if target_path == base_dir:
        raise IsADirectoryError("Security Error: Target path cannot be the base directory itself.")
    return base_folder + "/" + user_path


def read_file_content_and_type(filepath: str, binary: bool = False) -> tuple[str, bool, str]:
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
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), False, ""


def get_embedding(text_or_image_url: str, is_image: bool = False) -> List[float]:
    """Fetch embedding vector for a given text or image from the Llama Server."""
    if is_image:
        payload = {"content": [{"prompt_string": MEDIA_MARKER, "multimodal_data": [text_or_image_url]}]}
    else:
        payload = {"content": [{"prompt_string": text_or_image_url, "multimodal_data": []}]}

    req = urllib.request.Request(LLAMA_EMBED_URL, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode("utf-8"))
        if isinstance(result, dict) and "data" in result:
            return result["data"][0]["embedding"]
        elif isinstance(result, list):
            sorted_data = sorted(result, key=lambda x: x.get("index", 0))
            emb = sorted_data[0].get("embedding", [])
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


def get_category_path_id(category_path: str):
    """Parse a hierarchical category path (e.g. 'Science/Physics') and ensure it exists, returning leaf ID."""
    if not category_path:
        return 0
    
    parts = [p.strip() for p in category_path.split('/') if p.strip()]
    parent_id = None
    
    for part in parts:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            if parent_id is None:
                cur.execute("SELECT id FROM `node_category` WHERE name = ? AND parent__category__id IS NULL", (part,))
            else:
                cur.execute("SELECT id FROM `node_category` WHERE name = ? AND parent__category__id = ?", (part, parent_id))
            row = cur.fetchone()
            
            if row:
                parent_id = row[0]
            else:
                if parent_id is None:
                    cur.execute("INSERT INTO `node_category` (name) VALUES (?)", (part,))
                else:
                    cur.execute("INSERT INTO `node_category` (name, parent__category__id) VALUES (?, ?)", (part, parent_id))
                cur.execute("SELECT LAST_INSERT_ID()")
                parent_id = cur.fetchone()[0]
                conn.commit()
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
                
    return parent_id or 0


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
        print(f"Error: Could not check node category: {e}", file=sys.stderr)


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
                """
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
    categoryId = get_category_path_id(category)
    if categoryId == 0:
        return 0

    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            query = "INSERT INTO `node_x_category` (node__id, category__id) VALUES (?, ?)"
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
    categoryId = get_category_path_id(category)
    if categoryId == 0:
        return

    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            query = "DELETE FROM `node_x_category` WHERE node__id=? AND category__id=?"
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

            cur.execute("SELECT document FROM `node` WHERE id=?", (nodeId,))
            row = cur.fetchone()
            if row:
                filepath = get_safe_path(MEMORY_DIR, row[0])
                if os.path.exists(filepath):
                    os.remove(filepath)

            cur.execute("DELETE FROM `node` WHERE id=?", (nodeId,))
            cur.execute("DELETE FROM `node_relation` WHERE source__node__id=?", (nodeId,))
            cur.execute("DELETE FROM `node_relation` WHERE target__node__id=?", (nodeId,))
            cur.execute("DELETE FROM `node_x_category` WHERE node__id=?", (nodeId,))
            conn.commit()
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        return


def db_add_kg_relation(subject: str, predicate: str, object: str):
    """Save an explicit Knowledge Graph string triple."""
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT IGNORE INTO `kg_relation` (subject, predicate, object) VALUES (?, ?, ?)",
                (subject, predicate, object)
            )
            conn.commit()
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        print(f"Error saving kg relation: {e}", file=sys.stderr)


def db_search_kg_relations(entity: str) -> List[Dict[str, str]]:
    """Query Knowledge Graph for relations involving a specific entity."""
    results = []
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            like_term = f"%{entity}%"
            cur.execute(
                "SELECT subject, predicate, object FROM `kg_relation` WHERE subject LIKE ? OR object LIKE ?",
                (like_term, like_term)
            )
            for row in cur:
                results.append({"subject": row[0], "predicate": row[1], "object": row[2]})
            return results
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        print(f"Error querying kg relation: {e}", file=sys.stderr)
        return []


def get_node_id_by_title(title: str) -> Optional[int]:
    """Retrieve a node ID by its title."""
    if not title:
        return None
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM `node` WHERE title = ? LIMIT 1", (title,))
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        return None


def save_embedding_to_db(
    title: str,
    description: str,
    nodeType: str,
    doc_name: str,
    embedding: List[float],
    is_image: bool,
    parent_id: Optional[int] = None,
    valid_from: Optional[str] = None,
    valid_until: Optional[str] = None
):
    """Insert the document filename, its embedding, dates, and metadata into MariaDB."""
    nodeTypeId = get_node_type_id(nodeType)

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        emb_str = json.dumps(embedding)
        
        # Formatting NULL values safely for DB execution
        v_from = valid_from if valid_from else None
        v_until = valid_until if valid_until else None

        query = """
            INSERT INTO `node` 
            (node_type__id, parent__node__id, created_at, valid_from, valid_until, title, description, document, embedding) 
            VALUES (?, ?, NOW(), ?, ?, ?, ?, ?, VEC_FromText(?))
        """
        cur.execute(query, (nodeTypeId, parent_id, v_from, v_until, title, description, doc_name, emb_str))
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
    include_expired: bool = False
) -> List[Dict[str, Any]]:
    """Find top matching documents filtering by vectors, types, and temporal limits."""
    nodeTypeId = get_node_type_id(nodeType)
    nodeCategoryId = get_category_path_id(nodeCategory)

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        select_clause = """
            SELECT `node`.`id`, `node`.`node_type__id`, `node`.`created_at`, 
                   `node`.`description`, `node`.`document`, `node`.`title`, 
                   `node`.`valid_from`, `node`.`valid_until`, 
                   VEC_DISTANCE_COSINE(embedding, VEC_FromText(?)) as distance 
            FROM `node`
        """
        join_clause = ""
        where_clauses = []
        opt = [json.dumps(embedding)]

        if nodeTypeId:
            where_clauses.append("`node`.`node_type__id` = ?")
            opt.append(nodeTypeId)
        if nodeCategoryId:
            join_clause = "INNER JOIN `node_x_category` ON `node`.`id` = `node_x_category`.`node__id`"
            where_clauses.append("`node_x_category`.`category__id` = ?")
            opt.append(nodeCategoryId)

        if not include_expired:
            where_clauses.append("(`node`.`valid_from` IS NULL OR `node`.`valid_from` <= NOW())")
            where_clauses.append("(`node`.`valid_until` IS NULL OR `node`.`valid_until` >= NOW())")

        query = select_clause + " " + join_clause
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
            
        query += " ORDER BY distance ASC LIMIT ?"
        opt.append(limit)

        cur.execute(query, tuple(opt))
        
        results = []
        for row in cur:
            if row[8] < 0.6: # roughly 40% match
                results.append({
                    "id": row[0],
                    "type_id": row[1],
                    "created_at": row[2],
                    "description": row[3],
                    "document": row[4],
                    "title": row[5],
                    "valid_from": row[6],
                    "valid_until": row[7]
                })
        return results
    finally:
        if "conn" in locals() and conn.open:
            conn.close()


def search_db_by_id(node_id: int) -> List[Dict[str, Any]]:
    """Get node explicitly by id."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        query = """
            SELECT id, node_type__id, created_at, description, document, title, valid_from, valid_until
            FROM `node`
            WHERE id = ?            
        """
        cur.execute(query, (node_id,))
        results = []
        for row in cur:
            results.append({
                "id": row[0],
                "type_id": row[1],
                "created_at": row[2],
                "description": row[3],
                "document": row[4],
                "title": row[5],
                "valid_from": row[6],
                "valid_until": row[7]
            })
        return results
    finally:
        if "conn" in locals() and conn.open:
            conn.close()


def generate_documents_from_db_matches(db_matches: List[Dict[str, Any]]) -> List[Any]:
    """Reads actual files based on DB metadata and formats them as MCP Documents."""
    documents = []
    found_titles = set()

    for match in db_matches:
        fname = match["document"]
        filepath = get_safe_path(MEMORY_DIR, fname)
        
        if match.get("title"):
            found_titles.add(match["title"])

        if os.path.exists(filepath):
            nodeType = get_node_type_name(match["type_id"])
            
            # Use JSON to encapsulate metadata properly
            meta = {
                "id": match["id"],
                "title": match.get("title") or "",
                "description": match["description"] or "",
                "type": nodeType,
                "valid_from": str(match["valid_from"]) if match["valid_from"] else None,
                "valid_until": str(match["valid_until"]) if match["valid_until"] else None
            }
            documents.append(TextContent(type="text", text=json.dumps(meta)))

            ext = os.path.splitext(filepath)[1].lower()
            is_image = ext in [".png", ".jpeg", ".jpg"]
            if is_image:
                content, is_image, imageFormat = read_file_content_and_type(filepath, True)
                b64_data = base64.b64encode(content).decode("utf-8")
                documents.append(ImageContent(type="image", data=b64_data, mimeType=f"image/{imageFormat.lower()}"))
            else:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    documents.append(TextContent(type="text", text=content))

    # Agentic Bridging: Inject related Knowledge Graph relations automatically 
    if documents and found_titles:
        relations_context = []
        for title in found_titles:
            rels = db_search_kg_relations(title)
            for r in rels:
                relations_context.append(f"- {r['subject']} {r['predicate']} {r['object']}")
                
        if relations_context:
            unique_rels = list(set(relations_context))
            documents.append(TextContent(
                type="text", 
                text="--- Known Graph Relations for Retrieved Documents ---\n" + "\n".join(unique_rels)
            ))

    return documents


def recall_by_embedding(
    nodeCategory: str, nodeType: str, emb: List[float], limit: int = DB_SEARCH_LIMIT, include_expired: bool = False
) -> List[Any]:
    db_matches = search_db(nodeCategory, nodeType, emb, limit=limit, include_expired=include_expired)
    if not db_matches: return []
    return generate_documents_from_db_matches(db_matches)


def recall_by_id(node_id: int) -> List[Any]:
    db_matches = search_db_by_id(node_id)
    if not db_matches: return []
    return generate_documents_from_db_matches(db_matches)


# --- MCP Tools ---

if not READ_ONLY:

    @mcp.tool(name=f"{TOOL_PREFIX}remember")
    async def remember(
        info: str, title: str = "", description: str = "", type: str = "", 
        category: str = "", valid_from: str = "", valid_until: str = "", parent_title: str = ""
    ) -> str:
        """
        Use this tool to save new text information, facts, concepts, or knowledge into the long-term memory.
        Automatically limits scope based on valid_from/valid_until dates, and tracks document hierarchy.
        """
        try:
            now = datetime.now()
            date_folder = now.strftime("%Y-%m-%d")
            hour_folder = now.strftime("%H")
            doc_id = str(uuid.uuid4())
            rel_filename = f"{date_folder}/{hour_folder}/{doc_id}.txt"
            filepath = os.path.join(MEMORY_DIR, date_folder, hour_folder, f"{doc_id}.txt")
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(info)

            emb = get_embedding(info)
            parent_id = get_node_id_by_title(parent_title) if parent_title else None

            nodeId = save_embedding_to_db(
                title=title, description=description, nodeType=type, 
                doc_name=rel_filename, embedding=emb, is_image=False, 
                parent_id=parent_id, valid_from=valid_from, valid_until=valid_until
            )
            add_node_to_category(nodeId, category)

            return f"Memory successfully saved, node_id: {nodeId}."
        except Exception as e:
            return f"Error saving memory: {str(e)}"

    @mcp.tool(name=f"{TOOL_PREFIX}remember_file")
    async def remember_file(
        filename: str, title: str = "", description: str = "", type: str = "", 
        category: str = "", valid_from: str = "", valid_until: str = "", parent_title: str = ""
    ) -> str:
        """
        Use this tool to save an existing file in the Workspace to long-term memory with temporal & hierarchical limits.
        """
        try:
            original_filepath = get_safe_path(WORKSPACE_DIR, filename)
            if not os.path.exists(original_filepath):
                return f"Error: File '{filename}' not found in Workspace."

            now = datetime.now()
            date_folder = now.strftime("%Y-%m-%d")
            hour_folder = now.strftime("%H")

            doc_id = str(uuid.uuid4())
            _, ext = os.path.splitext(filename)
            rel_filename = f"{date_folder}/{hour_folder}/{doc_id}{ext}"
            new_filepath = os.path.join(MEMORY_DIR, date_folder, hour_folder, f"{doc_id}{ext}")
            os.makedirs(os.path.dirname(new_filepath), exist_ok=True)

            content, is_image, imageFormat = read_file_content_and_type(original_filepath)
            emb = get_embedding(content, is_image=is_image)
            shutil.copy2(original_filepath, new_filepath)

            parent_id = get_node_id_by_title(parent_title) if parent_title else None

            nodeId = save_embedding_to_db(
                title=title, description=description, nodeType=type, 
                doc_name=rel_filename, embedding=emb, is_image=is_image,
                parent_id=parent_id, valid_from=valid_from, valid_until=valid_until
            )
            add_node_to_category(nodeId, category)

            return f"Memory successfully saved, node_id: {nodeId}."
        except Exception as e:
            return f"Error saving file to memory: {str(e)}"

    @mcp.tool(name=f"{TOOL_PREFIX}save_relation")
    async def save_relation(subject: str, predicate: str, object: str) -> str:
        """
        Save a specific relational fact (Subject-Predicate-Object) to the explicit Knowledge Graph.
        Examples:
        - subject: "User", predicate: "has", object: "dog"
        - subject: "User", predicate: "goes", object: "shopping on 2026-05-15"
        """
        db_add_kg_relation(subject, predicate, object)
        return f"Saved relation: {subject} -> {predicate} -> {object}"

    @mcp.tool(name=f"{TOOL_PREFIX}create_relationship")
    async def create_relationship(source_id: int, target_id: int, relation: str) -> str:
        """Create a semantic structural relationship between two integer node IDs."""
        try:
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                cur.execute("INSERT INTO `node_relation` (source__node__id, target__node__id, relation) VALUES (?, ?, ?)", (source_id, target_id, relation))
                conn.commit()
                return f"Successfully linked node_id {source_id} to node_id {target_id} with relation '{relation}'."
            finally:
                if "conn" in locals() and conn.open: conn.close()
        except Exception as e:
            return f"Error linking nodes: {str(e)}"
        
    @mcp.tool(name=f"{TOOL_PREFIX}delete_relationship")
    async def delete_relationship(source_id: int, target_id: int) -> str:
        """Delete a semantic relationship between two integer node IDs."""
        try:
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM `node_relation` WHERE source__node__id=? AND target__node__id=?", (source_id, target_id))
                conn.commit()
                return f"Successfully deleted relation between node_id {source_id} and node_id {target_id}."
            finally:
                if "conn" in locals() and conn.open: conn.close()
        except Exception as e:
            return f"Error delete relation: {str(e)}"

    @mcp.tool(name=f"{TOOL_PREFIX}link_node_to_category")
    async def link_node_to_category(node_id: int, category: str) -> str:
        """Add an existing memory node to a specific hierarchical category (e.g., 'Science/Physics')."""
        rowId = add_node_to_category(node_id, category)
        if rowId:
            return f"Successfully linked node {node_id} to category '{category}'."
        return f"Error linking node."

    @mcp.tool(name=f"{TOOL_PREFIX}remove_node_from_category")
    async def remove_node_from_category(node_id: int, category: str) -> str:
        """Remove an existing memory node from a specific category."""
        remove_node_from_category(node_id, category)
        return f"Removed"

    @mcp.tool(name=f"{TOOL_PREFIX}delete_node")
    async def delete_node(node_id: int) -> str:
        """Delete an existing memory node explicitly."""
        db_delete_node(node_id)
        return f"Deleted"


@mcp.tool(name=f"{TOOL_PREFIX}get_entity_relations")
async def get_entity_relations(entity: str) -> str:
    """
    Query the explicit Knowledge Graph for relations involving a specific entity.
    Useful for multi-hop reasoning (e.g. checking what 'User' owns).
    """
    results = db_search_kg_relations(entity)
    if not results:
        return f"No relations found for '{entity}'."
    return "\n".join([f"- {r['subject']} {r['predicate']} {r['object']}" for r in results])


@mcp.tool(name=f"{TOOL_PREFIX}read_local_file")
async def read_local_file(filepath: str) -> str:
    """Read a local file directly from the Workspace directory."""
    try:
        safe_path = get_safe_path(WORKSPACE_DIR, filepath)
        if not os.path.exists(safe_path):
            return f"Error: File '{filepath}' not found in Workspace."
        content, _, _ = read_file_content_and_type(safe_path)
        return content
    except Exception as e:
        return f"Error reading file: {str(e)}"


@mcp.tool(name=f"{TOOL_PREFIX}recall")
async def recall(
    text_or_image_description: str,
    type: str = "",
    category: str = "",
    memories_limit: int = 8,
    include_expired: bool = False
) -> List[Any]:
    """
    Search the long-term memory. Automatically bridges explicit Knowledge Graph relations for retrieved matches.
    """
    try:
        emb = get_embedding(text_or_image_description)
        documents = recall_by_embedding(category, type, emb, memories_limit, include_expired)
        if not documents:
            return [TextContent(type="text", text="No memory found")]
        return documents
    except Exception as e:
        return [TextContent(type="text", text=f"Error recalling memory: {str(e)}")]


@mcp.tool(name=f"{TOOL_PREFIX}recall_by_file")
async def recall_by_file(
    filename: str, type: str = "", category: str = "", memories_limit: int = 8, include_expired: bool = False
) -> List[Any]:
    """Search the memory by comparing it against the contents of an existing file in the Workspace."""
    try:
        filepath = get_safe_path(WORKSPACE_DIR, filename)
        if not os.path.exists(filepath):
            return [TextContent(type="text", text=f"Error: File '{filename}' not found in Workspace.")]

        content, is_image, imageFormat = read_file_content_and_type(filepath)
        emb = get_embedding(content, is_image=is_image)

        documents = recall_by_embedding(category, type, emb, memories_limit, include_expired)
        if not documents:
            return [TextContent(type="text", text="No memory found")]
        return documents
    except Exception as e:
        return [TextContent(type="text", text=f"Error recalling by file: {str(e)}")]


@mcp.tool(name=f"{TOOL_PREFIX}recall_by_node_id")
async def recall_by_node_id(node_id: int) -> List[Any]:
    """Get the content of a specific node explicitely from memory using its integer ID."""
    try:
        documents = recall_by_id(node_id)
        if not documents:
            return [TextContent(type="text", text="No memory found")]
        return documents
    except Exception as e:
        return [TextContent(type="text", text=f"Error recalling by node id: {str(e)}")]


@mcp.tool(name=f"{TOOL_PREFIX}get_node_relations")
async def get_node_relations(node_id: int) -> List[Any]:
    """Explore structural hierarchy links for an integer node ID (incoming/outgoing node relationships)."""
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
                results.append(json.dumps({"direction": row[0], "relation": row[2], "node_id": row[1]}))

            if not results:
                return [TextContent(type="text", text=f"No relations found for memory node_id: {node_id}")]

            header = f"Relations for memory node_id: {node_id}\n"
            return [TextContent(type="text", text=header + "\n".join(results))]
        finally:
            if "conn" in locals() and conn.open:
                conn.close()
    except Exception as e:
        return [TextContent(type="text", text=f"Error getting node relations: {str(e)}")]


@mcp.tool(name=f"{TOOL_PREFIX}get_node_category")
async def get_node_category(node_id: int) -> List[Any]:
    """Get categories assigned to a specific memory node."""
    results = get_node_category_list(node_id)
    if not results:
        return [TextContent(type="text", text=f"No category found for memory node_id: {node_id}")]
    header = f"Categories for memory node_id: {node_id}\n"
    return [TextContent(type="text", text=header + ", ".join([r["name"] for r in results]))]


@mcp.tool(name=f"{TOOL_PREFIX}category_exists")
async def category_exists(name: str) -> str:
    """Check if a category with the specified name exists."""
    if has_category(name) == 0:
        return f"Category with name '{name}' does not exists."
    return f"Category with name '{name}' found."


@mcp.tool(name=f"{TOOL_PREFIX}get_current_datetime")
async def get_current_datetime() -> str:
    """
    Get the current system date and time.
    Use this as a temporal anchor to understand 'now' when filtering or saving memories with valid_from/valid_until constraints.
    """
    return datetime.now().isoformat()


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
    parser = argparse.ArgumentParser(description="Memory MCP Server")
    parser.add_argument("--stdio", action="store_true", help="Run the MCP server in standard stdio mode")
    parser.add_argument("--mcp", action="store_true", help="Run the MCP server in HTTP/SSE mode (default)")
    parser.add_argument("--api-key", type=str, help="Enforce API key authentication in HTTP mode")
    parser.add_argument("--env-base", type=str, default="", help="Prefix for environment variables")
    parser.add_argument("--read-only", action="store_true", help="Disable write functionality")
    parser.add_argument("--tool-prefix", type=str, default="memory_", help="Prefix for MCP tool")
    parser.add_argument("--media-marker", type=str, default="<__media__>", help="Media marker for image embeddings")
    parser.add_argument("--mcp-name", type=str, default="Memory", help="MCP name, default: Memory")

    args = parser.parse_args()

    if ENV_PREFIX:
        actual_prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        print(f"Using environment variable prefix: '{actual_prefix}'", file=sys.stderr)

    if READ_ONLY:
        print("Server is running in READ-ONLY mode (write tools disabled).", file=sys.stderr)

    if args.stdio:
        print("Starting Memory MCP Server in STDIO mode...", file=sys.stderr)
        mcp.run()
    else:
        print(f"Starting Memory MCP Server in HTTP mode on port {PORT}...", file=sys.stderr)
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