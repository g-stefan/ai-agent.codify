-- MCP Task (SQLite Schema)
-- SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
-- SPDX-License-Identifier: Apache-2.0

CREATE TABLE IF NOT EXISTS project (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'active', -- active, archived
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    parent_task_id INTEGER DEFAULT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'pending', -- pending, in_progress, blocked, completed
    priority INTEGER DEFAULT 0, -- Higher number = higher priority
    task_order INTEGER DEFAULT 0, -- Execution sequence (lower number = do first)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES project (id) ON DELETE CASCADE,
    FOREIGN KEY (parent_task_id) REFERENCES task (id) ON DELETE CASCADE
);

-- SQLite Triggers to emulate MariaDB's ON UPDATE CURRENT_TIMESTAMP
CREATE TRIGGER IF NOT EXISTS trg_project_updated_at
AFTER UPDATE ON project
BEGIN
    UPDATE project SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_task_updated_at
AFTER UPDATE ON task
BEGIN
    UPDATE task SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_task_project ON task (project_id);
CREATE INDEX IF NOT EXISTS idx_task_parent ON task (parent_task_id);
CREATE INDEX IF NOT EXISTS idx_task_status ON task (status);