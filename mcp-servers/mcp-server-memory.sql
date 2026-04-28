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
	`created_at` DATETIME NULL,
        `description` VARCHAR(252) NULL,
        `document` VARCHAR(252) NULL,
        `embedding` VECTOR(2048) NOT NULL,        
        VECTOR INDEX (`embedding`) M=8 DISTANCE=cosine
);

CREATE TABLE `node_relation` (
        `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
	`source__node__id` BIGINT UNSIGNED NOT NULL DEFAULT 0,
        `target__node__id` BIGINT UNSIGNED NOT NULL DEFAULT 0,
        `relation` VARCHAR(128) NULL        
);

CREATE TABLE `node_category` (
        `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        `name` VARCHAR(128) NULL
);

CREATE TABLE `node_x_category` (
        `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
	`node__id` BIGINT UNSIGNED NOT NULL DEFAULT 0,
        `category__id` BIGINT UNSIGNED NOT NULL DEFAULT 0        
);

