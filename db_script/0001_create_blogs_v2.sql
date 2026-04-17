-- clean up any leftover state from a previous failed run
DROP TABLE IF EXISTS blogs_new;

-- create new table with desired schema (example: include other columns explicitly)
CREATE TABLE IF NOT EXISTS blogs_new (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    slug      TEXT NOT NULL UNIQUE,
    title     TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    thumbnail TEXT NOT NULL DEFAULT '',
    content   TEXT NOT NULL DEFAULT '',
    createdAt DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

INSERT INTO blogs_new (id, slug, title, description, thumbnail, content, createdAt)
SELECT id, slug, title, description, thumbnail, content, COALESCE(createdAt, CURRENT_TIMESTAMP)
FROM blogs;

DROP TABLE blogs;
ALTER TABLE blogs_new RENAME TO blogs;