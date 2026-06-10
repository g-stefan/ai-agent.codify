-- MCP ToDo SQLite Equivilant Schema
-- (This schema is automatically executed and managed by the python script)
-- SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
-- SPDX-License-Identifier: Apache-2.0

-- Create the main todos table
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
    
    -- Foreign Key to support subtasks cascading deletion
    CONSTRAINT `fk_parent` FOREIGN KEY (`parent_id`) REFERENCES `todos`(`id`) ON DELETE CASCADE
);

-- Trigger to simulate `ON UPDATE CURRENT_TIMESTAMP` present in MariaDB
CREATE TRIGGER IF NOT EXISTS update_todos_updated_at
AFTER UPDATE ON todos
FOR EACH ROW
BEGIN
    UPDATE todos SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- Indexes for faster searching and relations
CREATE INDEX IF NOT EXISTS idx_title ON todos(title);
CREATE INDEX IF NOT EXISTS idx_category ON todos(category);
CREATE INDEX IF NOT EXISTS idx_parent_id ON todos(parent_id);
CREATE INDEX IF NOT EXISTS idx_task_order ON todos(task_order);
CREATE INDEX IF NOT EXISTS idx_created_at ON todos(created_at);
CREATE INDEX IF NOT EXISTS idx_is_completed ON todos(is_completed);
CREATE INDEX IF NOT EXISTS idx_due_date ON todos(due_date);