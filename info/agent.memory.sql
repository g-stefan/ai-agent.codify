-- SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
-- SPDX-License-Identifier: Unlicense

CREATE TABLE embeddings (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
	created_at DATETIME NULL,
        document VARCHAR(128) NULL,
        embedding VECTOR(2048) NOT NULL,
        VECTOR INDEX (embedding) M=8 DISTANCE=cosine
);
