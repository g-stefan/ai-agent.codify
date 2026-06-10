-- MCP ToDo
-- SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
-- SPDX-License-Identifier: Apache-2.0

-- Create the main todos table
CREATE TABLE IF NOT EXISTS `todos` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `title` VARCHAR(255) NOT NULL,
    `description` TEXT,
    `is_completed` TINYINT(1) DEFAULT 0,
    `priority` ENUM('low', 'medium', 'high') DEFAULT 'medium',
    `due_date` DATE NULL,
    `category` VARCHAR(100) DEFAULT NULL,
    `parent_id` INT DEFAULT NULL,
    `task_order` INT DEFAULT 0,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- Foreign Key to support subtasks cascading deletion
    CONSTRAINT `fk_parent` FOREIGN KEY (`parent_id`) REFERENCES `todos`(`id`) ON DELETE CASCADE,
    
    -- Indexes for faster searching and relations
    INDEX `idx_title` (`title`),
    INDEX `idx_category` (`category`),
    INDEX `idx_parent_id` (`parent_id`),
    INDEX `idx_task_order` (`task_order`),
    INDEX `idx_created_at` (`created_at`),
    INDEX `idx_is_completed` (`is_completed`),
    INDEX `idx_due_date` (`due_date`)
);
