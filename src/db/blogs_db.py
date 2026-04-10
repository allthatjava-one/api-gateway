"""
blogs_db — D1 database queries for the blogs table.
"""


async def get_blogs(db) -> list:
    """Fetch all blogs ordered by id. Returns a list of dicts."""
    result = await db.prepare(
        "SELECT slug, title, description, thumbnail FROM blogs ORDER BY id"
    ).all()
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
        "SELECT slug, title, content FROM blogs WHERE slug = ?1"
    ).bind(slug).first()
    if row is None:
        return None
    return row.to_py()
