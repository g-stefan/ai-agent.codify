-- MCP Memory (Lightweight Knowledge Graph)
-- SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
-- SPDX-License-Identifier: Apache-2.0

CREATE TABLE `node_type` (
        `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        `name` VARCHAR(128) NULL
);

CREATE TABLE `node` (
        `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        `node_type__id` BIGINT UNSIGNED NOT NULL DEFAULT 0,
        `parent__node__id` BIGINT UNSIGNED NULL,
        `created_at` DATETIME NULL,
        `valid_from` DATETIME NULL,
        `valid_until` DATETIME NULL,
        `title` VARCHAR(255) NULL,
        `description` VARCHAR(252) NULL,
        `document` VARCHAR(252) NULL,
        `embedding` VECTOR(2048) NOT NULL,        
        VECTOR INDEX (`embedding`) M=8 DISTANCE=cosine,
        FOREIGN KEY (`parent__node__id`) REFERENCES `node`(`id`) ON DELETE SET NULL
);

-- Semantic node-to-node relationships
CREATE TABLE `node_relation` (
        `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        `source__node__id` BIGINT UNSIGNED NOT NULL DEFAULT 0,
        `target__node__id` BIGINT UNSIGNED NOT NULL DEFAULT 0,
        `relation` VARCHAR(128) NULL        
);

-- Explicit String-based Knowledge Graph Relations (Subject-Predicate-Object)
CREATE TABLE `kg_relation` (
        `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        `subject` VARCHAR(255) NOT NULL,
        `predicate` VARCHAR(255) NOT NULL,
        `object` VARCHAR(255) NOT NULL,
        UNIQUE KEY `uk_spo` (`subject`, `predicate`, `object`)
);

CREATE TABLE `node_category` (
        `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        `parent__category__id` BIGINT UNSIGNED NULL,
        `name` VARCHAR(128) NULL,
        FOREIGN KEY (`parent__category__id`) REFERENCES `node_category`(`id`) ON DELETE SET NULL
);

CREATE TABLE `node_x_category` (
        `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        `node__id` BIGINT UNSIGNED NOT NULL DEFAULT 0,
        `category__id` BIGINT UNSIGNED NOT NULL DEFAULT 0        
);