"""
blogs_db — D1 database queries for the blogs table.
"""


async def get_blogs(db, limit: int | None = None, offset: int = 0) -> list:
    """Fetch blogs ordered by id with optional pagination. Returns a list of dicts.

    If `limit` is None, returns all rows.
    """
    if limit is None:
        stmt = "SELECT slug, title, description, thumbnail, createdAt FROM blogs ORDER  BY createdAt DESC"
        result = await db.prepare(stmt).all()
    else:
        stmt = (
            "SELECT slug, title, description, thumbnail, createdAt FROM blogs "
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
    row = await db.prepare(
        "SELECT slug, title, content, createdAt FROM blogs WHERE slug = ?1"
    ).bind(slug).first()
    if row is None:
        return None
    return row.to_py()


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
