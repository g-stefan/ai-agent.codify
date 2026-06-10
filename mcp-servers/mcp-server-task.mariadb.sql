-- MCP Task
-- SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
-- SPDX-License-Identifier: Apache-2.0

CREATE TABLE IF NOT EXISTS `project` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(255) NOT NULL,
    `description` TEXT,
    `status` VARCHAR(50) DEFAULT 'active', -- active, archived
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `task` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `project_id` INT NOT NULL,
    `parent_task_id` INT DEFAULT NULL,
    `title` VARCHAR(255) NOT NULL,
    `description` TEXT,
    `status` VARCHAR(50) DEFAULT 'pending', -- pending, in_progress, blocked, completed
    `priority` INT DEFAULT 0, -- Higher number = higher priority
    `task_order` INT DEFAULT 0, -- Execution sequence (lower number = do first)
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    CONSTRAINT `fk_task_project`
        FOREIGN KEY (`project_id`)
        REFERENCES `project` (`id`)
        ON DELETE CASCADE,
        
    CONSTRAINT `fk_task_parent`
        FOREIGN KEY (`parent_task_id`)
        REFERENCES `task` (`id`)
        ON DELETE CASCADE
);

-- Indexes for faster lookups
CREATE INDEX `idx_task_project` ON `task` (`project_id`);
CREATE INDEX `idx_task_parent` ON `task` (`parent_task_id`);
CREATE INDEX `idx_task_status` ON `task` (`status`);