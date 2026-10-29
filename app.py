
import os
import json
import sqlite3
from pathlib import Path

from datetime import datetime

import fitz
import streamlit as st

BASE_DIR = Path.home() / "smart-file-system"
DB_PATH = BASE_DIR / "file_index.db"
SUPPORTED = {".txt", ".pdf"}
XATTR = "user.semantic_tags"

BASE_DIR.mkdir(parents=True, exist_ok=True)


def initialize_database():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                name TEXT,
                extension TEXT,
                size INTEGER,
                modified TEXT,
                summary TEXT,
                tags TEXT
            )
        """)


def extract_text(path):
    try:
        if path.suffix.lower() == ".txt":
            return path.read_text(
                encoding="utf-8", errors="replace"
            )[:10000]

        if path.suffix.lower() == ".pdf":
            chunks = []
            total = 0
            with fitz.open(path) as pdf:
                for page in pdf:
                    chunk = page.get_text()
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= 10000:
                        break
            return "\n".join(chunks)[:10000]

    except Exception:
        return ""

    return ""


def generate_tags(content):
    text = content.lower()

    categories = {
        "lecture_notes": [
            "lecture", "chapter", "syllabus", "notes"
        ],
        "report": [
            "report", "analysis", "conclusion", "results"
        ],
        "todo_list": [
            "todo", "to-do", "tasks", "deadline"
        ],
        "operating_systems": [
            "operating system", "process scheduling",
            "deadlock", "memory management"
        ],
        "database": [
            "database", "sql", "normalization", "query"
        ]
    }

    tags = [
        tag for tag, words in categories.items()
        if any(word in text for word in words)
    ]

    return tags or ["uncategorized"]


def save_xattr(path, tags):
    try:
        os.setxattr(
            str(path),
            XATTR,
            json.dumps(tags).encode("utf-8")
        )
        return True
    except (OSError, AttributeError, NotImplementedError):
        return False


def scan_directory(directory):
    root = Path(directory).expanduser().resolve()

    if not root.is_dir():
        raise ValueError("The directory does not exist.")

    indexed = 0
    errors = 0

    with sqlite3.connect(DB_PATH) as conn:
        for current, _, filenames in os.walk(root):
            for filename in filenames:
                path = Path(current) / filename

                if path.suffix.lower() not in SUPPORTED:
                    continue

                try:
                    info = path.stat()
                    content = extract_text(path)
                    tags = generate_tags(content)
                    summary = " ".join(content.split())[:250]
                    modified = datetime.fromtimestamp(
                        info.st_mtime
                    ).isoformat(timespec="seconds")

                    conn.execute("""
                        INSERT OR REPLACE INTO files
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        str(path), path.name,
                        path.suffix.lower(), info.st_size,
                        modified, summary, json.dumps(tags)
                    ))

                    save_xattr(path, tags)
                    indexed += 1

                except (OSError, sqlite3.Error):
                    errors += 1

    return indexed, errors


def search_files(query):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        if query.strip():
            term = "%" + query.strip() + "%"
            rows = conn.execute("""
                SELECT * FROM files
                WHERE name LIKE ?
                   OR path LIKE ?
                   OR summary LIKE ?
                   OR tags LIKE ?
                ORDER BY name
            """, (term, term, term, term)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM files ORDER BY name"
            ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        item["tags"] = json.loads(item["tags"])
        results.append(item)

    return results


st.set_page_config(
    page_title="Smart File System",
    page_icon="📁",
    layout="wide"
)

initialize_database()

st.title("📁 Smart File System")
st.caption("Linux file indexing and semantic tagging")

st.subheader("1. Scan directory")

directory = st.text_input(
    "Directory path",
    str(BASE_DIR / "test_files")
)

if st.button("Scan and Index Files"):
    try:
        with st.spinner("Scanning files..."):
            count, errors = scan_directory(directory)

        st.success(f"Indexed {count} file(s).")
        if errors:
            st.warning(f"{errors} file(s) could not be processed.")
    except (ValueError, OSError) as exc:
        st.error(str(exc))

st.divider()
st.subheader("2. Search files")

query = st.text_input(
    "Search by filename, topic, summary or tag",
    placeholder="Example: operating_systems"
)

results = search_files(query)
st.write(f"Found {len(results)} result(s).")

if results:
    display_rows = [{
        "File Name": item["name"],
        "Extension": item["extension"],
        "Size (bytes)": item["size"],
        "Tags": ", ".join(item["tags"]),
        "Summary": item["summary"],
        "Path": item["path"]
    } for item in results]

    st.dataframe(
        display_rows,
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No matching files. Scan a directory first.")

st.divider()
st.caption(
    "OS concepts: file I/O, directory traversal, "
    "metadata indexing and extended attributes."
)
