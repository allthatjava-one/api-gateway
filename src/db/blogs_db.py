"""
blogs_db — D1 database queries for the blogs table.
"""


async def get_blogs(db, limit: int | None = None, offset: int = 0) -> list:
    """Fetch blogs ordered by id with optional pagination. Returns a list of dicts.

    If `limit` is None, returns all rows.
    """
    if limit is None:
        stmt = "SELECT slug, title, description, thumbnail, createdAt, title_fr, title_es, title_ko, description_fr, description_es, description_ko FROM blogs ORDER  BY createdAt DESC"
        result = await db.prepare(stmt).all()
    else:
        stmt = (
            "SELECT slug, title, description, thumbnail, createdAt, title_fr, title_es, title_ko, description_fr, description_es, description_ko FROM blogs "
            "ORDER BY createdAt DESC LIMIT ?1 OFFSET ?2"
        )
        result = await db.prepare(stmt).bind(limit, offset).all()
    blogs = result.results.to_py()
    try:
        print(f"[blogs] fetched {len(blogs)} rows from DB")
        if len(blogs) > 0:
            print(f"[blogs] first row keys: {list(blogs[0].keys())}")
    except Exception:
        print("[blogs] fetched rows (unable to show length)")
    return blogs


async def get_blog_by_slug(db, slug: str):
    """Fetch a single blog by slug. Returns a dict or None if not found."""
    stmt = (
        "WITH ordered AS ("
        "  SELECT slug, title, content, createdAt, title_fr, title_es, title_ko, "
        "         content_fr, content_es, content_ko, "
        "         LAG(slug) OVER (ORDER BY createdAt DESC, id ASC) AS previous_slug, "
        "         LAG(title) OVER (ORDER BY createdAt DESC, id ASC) AS previous_title, "
        "         LAG(title_fr) OVER (ORDER BY createdAt DESC, id ASC) AS previous_title_fr, "
        "         LAG(title_es) OVER (ORDER BY createdAt DESC, id ASC) AS previous_title_es, "
        "         LAG(title_ko) OVER (ORDER BY createdAt DESC, id ASC) AS previous_title_ko, "
        "         LEAD(slug) OVER (ORDER BY createdAt DESC, id ASC) AS next_slug, "
        "         LEAD(title) OVER (ORDER BY createdAt DESC, id ASC) AS next_title, "
        "         LEAD(title_fr) OVER (ORDER BY createdAt DESC, id ASC) AS next_title_fr, "
        "         LEAD(title_es) OVER (ORDER BY createdAt DESC, id ASC) AS next_title_es, "
        "         LEAD(title_ko) OVER (ORDER BY createdAt DESC, id ASC) AS next_title_ko "
        "  FROM blogs"
        ") SELECT slug, title, content, createdAt, title_fr, title_es, title_ko, "
        "content_fr, content_es, content_ko, previous_slug, previous_title, previous_title_fr, previous_title_es, previous_title_ko, "
        "next_slug, next_title, next_title_fr, next_title_es, next_title_ko FROM ordered WHERE slug = ?1"
    )
    row = await db.prepare(stmt).bind(slug).first()
    if row is None:
        return None

    data = row.to_py()
    # Extract neighboring slugs and reshape into nested objects per API design
    prev_slug = data.pop("previous_slug", None)
    prev_title = data.pop("previous_title", None)
    prev_title_fr = data.pop("previous_title_fr", None)
    prev_title_es = data.pop("previous_title_es", None)
    prev_title_ko = data.pop("previous_title_ko", None)

    next_slug = data.pop("next_slug", None)
    next_title = data.pop("next_title", None)
    next_title_fr = data.pop("next_title_fr", None)
    next_title_es = data.pop("next_title_es", None)
    next_title_ko = data.pop("next_title_ko", None)

    data["previous"] = (
        {
            "slug": prev_slug,
            "title": prev_title,
            "title_fr": prev_title_fr,
            "title_es": prev_title_es,
            "title_ko": prev_title_ko,
        }
        if prev_slug
        else None
    )

    data["next"] = (
        {
            "slug": next_slug,
            "title": next_title,
            "title_fr": next_title_fr,
            "title_es": next_title_es,
            "title_ko": next_title_ko,
        }
        if next_slug
        else None
    )
    return data


async def count_blogs(db) -> int:
    """Return total number of blogs as an integer."""
    # D1 supports simple scalar queries; use SELECT COUNT(*)
    result = await db.prepare("SELECT COUNT(*) AS cnt FROM blogs").first()
    if result is None:
        return 0
    try:
        row = result.to_py()
        # Depending on driver, COUNT may be returned as int or numeric key
        return int(row.get("cnt") or row.get("COUNT(*)") or 0)
    except Exception:
        return 0
