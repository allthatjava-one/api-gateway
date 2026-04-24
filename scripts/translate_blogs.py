"""
One-off script: translate blogs title/description/content to fr/es/ko
and update thrj-blogs-dev D1 table via wrangler.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from deep_translator import GoogleTranslator

DB_NAME = "thrj-blogs-dev"
WRANGLER_ROOT = Path(__file__).parent.parent
SQL_OUTPUT = WRANGLER_ROOT / "db_script" / "0004_i18n_content_data.sql"


def wrangler(*args: str) -> subprocess.CompletedProcess:
    cmd = ["cmd", "/c", "npx", "-y", "wrangler", "d1", "execute", DB_NAME, "--remote", *args]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(WRANGLER_ROOT),
    )


def run_query(sql: str) -> list[dict]:
    p = wrangler("--json", "--command", sql)
    if p.returncode != 0:
        print("STDOUT:", p.stdout)
        print("STDERR:", p.stderr)
        raise RuntimeError("Wrangler query failed")
    payload = json.loads(p.stdout)
    return payload[0].get("results", []) if payload else []


def run_sql_file(path: Path) -> str:
    p = wrangler("--file", str(path))
    if p.returncode != 0:
        print("STDOUT:", p.stdout)
        print("STDERR:", p.stderr)
        raise RuntimeError("Wrangler file execution failed")
    return p.stdout


def q(text: str) -> str:
    return (text or "").replace("'", "''")


CHUNK_SIZE = 4900  # Google Translate free endpoint limit
import re as _re

# HTML block-level tags we can safely split after
_SPLIT_PATTERN = _re.compile(r"(</(?:p|li|h[1-6]|div|ul|ol|blockquote|pre|tr|td|th|br\s*/?)>)", _re.IGNORECASE)


def _translate_once(text: str, target: str) -> str:
    for attempt in range(3):
        try:
            result = GoogleTranslator(source="auto", target=target).translate(text)
            return result or ""
        except Exception as exc:
            if attempt == 2:
                raise RuntimeError(f"Translation failed after 3 attempts ({target}): {exc}") from exc
            time.sleep(1.5 * (attempt + 1))
    return ""


def translate(text: str, target: str) -> str:
    if not text:
        return ""
    if len(text) <= CHUNK_SIZE:
        try:
            return _translate_once(text, target)
        except RuntimeError as exc:
            print(f"  [WARN] {exc}")
            return ""
    chunks = _split_text(text)
    translated_parts: list[str] = []
    for chunk in chunks:
        try:
            translated_parts.append(_translate_once(chunk, target))
            time.sleep(0.3)  # be polite between chunks
        except RuntimeError as exc:
            print(f"  [WARN] {exc}")
            translated_parts.append(chunk)  # fall back to original chunk
    return "".join(translated_parts)


def _split_text(text: str) -> list[str]:
    """Split text into <=CHUNK_SIZE pieces, preferring HTML tag boundaries."""
    if len(text) <= CHUNK_SIZE:
        return [text]

    # Try splitting on HTML block close-tags first
    parts = _SPLIT_PATTERN.split(text)
    # Merge the tag back onto the preceding segment
    merged: list[str] = []
    i = 0
    while i < len(parts):
        seg = parts[i]
        if i + 1 < len(parts) and _SPLIT_PATTERN.fullmatch(parts[i + 1]):
            seg += parts[i + 1]
            i += 2
        else:
            i += 1
        merged.append(seg)

    result: list[str] = []
    current = ""
    for seg in merged:
        if current and len(current) + len(seg) > CHUNK_SIZE:
            result.append(current)
            current = seg
        else:
            current += seg
    if current:
        result.append(current)

    # Final safety pass: hard-split any chunk that is still too large
    final: list[str] = []
    for chunk in result:
        while len(chunk) > CHUNK_SIZE:
            final.append(chunk[:CHUNK_SIZE])
            chunk = chunk[CHUNK_SIZE:]
        if chunk:
            final.append(chunk)
    return final


def main():
    print("Fetching rows from blogs …")
    rows = run_query("SELECT id, title, description, content FROM blogs ORDER BY id;")
    if not rows:
        print("No rows found – nothing to do.")
        sys.exit(0)

    print(f"Found {len(rows)} rows. Translating …")
    stmts: list[str] = []
    for i, row in enumerate(rows, 1):
        blog_id = int(row["id"])
        title = row.get("title") or ""
        desc = row.get("description") or ""
        content = row.get("content") or ""
        print(f"  [{i}/{len(rows)}] id={blog_id}: {title[:50]}")

        t_fr = translate(title, "fr")
        t_es = translate(title, "es")
        t_ko = translate(title, "ko")
        d_fr = translate(desc, "fr")
        d_es = translate(desc, "es")
        d_ko = translate(desc, "ko")
        c_fr = translate(content, "fr")
        c_es = translate(content, "es")
        c_ko = translate(content, "ko")

        stmts.append(
            f"UPDATE blogs SET "
            f"title_fr='{q(t_fr)}', "
            f"title_es='{q(t_es)}', "
            f"title_ko='{q(t_ko)}', "
            f"description_fr='{q(d_fr)}', "
            f"description_es='{q(d_es)}', "
            f"description_ko='{q(d_ko)}', "
            f"content_fr='{q(c_fr)}', "
            f"content_es='{q(c_es)}', "
            f"content_ko='{q(c_ko)}' "
            f"WHERE id={blog_id};"
        )

    sql = "\n".join(stmts) + "\n"

    # Persist a copy for review
    SQL_OUTPUT.write_text(sql, encoding="utf-8")
    print(f"\nSQL written to {SQL_OUTPUT}")

    print("Executing updates on remote D1 …")
    out = run_sql_file(SQL_OUTPUT)
    print(out.encode("ascii", errors="replace").decode("ascii"))
    print(f"Done. {len(stmts)} rows updated.")


if __name__ == "__main__":
    main()
