-- Add internationalization fields for French, Spanish, and Korean
ALTER TABLE blogs ADD COLUMN title_fr       TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN title_es       TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN title_ko       TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN description_fr TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN description_es TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN description_ko TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN content_fr TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN content_es TEXT NOT NULL DEFAULT '';
ALTER TABLE blogs ADD COLUMN content_ko TEXT NOT NULL DEFAULT '';
