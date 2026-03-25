-- SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
-- SPDX-License-Identifier: Unlicense

CREATE TABLE `embeddings` (
        `id` BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
	`created_at` DATETIME NULL,
        `document` VARCHAR(128) NULL,
        `type` INT UNSIGNED NOT NULL DEFAULT 0,
        `embedding` VECTOR(2048) NOT NULL,        
        VECTOR INDEX (`embedding`) M=8 DISTANCE=cosine
);

--- 
--- DB_TYPE_UNKNOWN = 0
--- DB_TYPE_TEXT = 1
--- DB_TYPE_IMAGE = 2
---
