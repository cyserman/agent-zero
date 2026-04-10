#!/usr/bin/env python3
"""
migrate_faiss_to_supabase.py — one-time migration of Agent Zero FAISS memories
to Supabase pgvector.

Run this BEFORE wiping your Docker volume or switching to the Supabase backend.
It reads every FAISS index under usr/memory/ (and projects), extracts the raw
document text + embeddings, and upserts them into Supabase's
agent_zero_memories table — no re-embedding required.

Usage (inside the Docker container):
    python3 /a0/scripts/migrate_faiss_to_supabase.py

Usage (from the host machine):
    docker exec Angee python3 /a0/scripts/migrate_faiss_to_supabase.py

Environment variables (auto-read from usr/.env, or set in the shell):
    SUPABASE_URL  — e.g. https://xxxx.supabase.co
    SUPABASE_KEY  — anon key (or service_role key for bypass RLS)

Prerequisites inside the container:
    pip install supabase       # already in requirements.txt on this branch
    pip install faiss-cpu      # already present in Agent Zero's image
"""

from __future__ import annotations

import os
import sys
import pickle
import re

# ── Repo root on sys.path so helpers resolve cleanly ──────────────────────────
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# Monkey-patch for faiss on Python 3.12 ARM (must come before faiss import)
try:
    from python.helpers import faiss_monkey_patch  # noqa: F401
except Exception:
    pass

import numpy as np

# ── Read usr/.env without pulling in the whole Agent Zero stack ───────────────
USR_DIR = os.path.join(REPO_ROOT, "usr")
TABLE = "agent_zero_memories"


def _read_dotenv(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    if not os.path.isfile(path):
        return env
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r'^([A-Za-z0-9_]+)\s*=\s*(.+)$', line)
            if m:
                env[m.group(1)] = m.group(2).strip('"').strip("'")
    return env


_dot = _read_dotenv(os.path.join(USR_DIR, ".env"))
SUPABASE_URL = _dot.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = _dot.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY", "")


# ─────────────────────────────────────────────────────────────────────────────
# FAISS discovery + loading
# ─────────────────────────────────────────────────────────────────────────────

def find_faiss_indexes() -> list[tuple[str, str]]:
    """
    Walk usr/memory/ and usr/projects/*/memory/ looking for index.faiss files.

    Returns list of (subdir_label, abs_folder_path) tuples where subdir_label
    matches the string used in the Supabase 'subdir' column.
    """
    found: list[tuple[str, str]] = []

    # Standard subdirs: usr/memory/<name>/
    memory_root = os.path.join(USR_DIR, "memory")
    if os.path.isdir(memory_root):
        for entry in sorted(os.scandir(memory_root), key=lambda e: e.name):
            if entry.is_dir(follow_symlinks=True):
                if os.path.isfile(os.path.join(entry.path, "index.faiss")):
                    found.append((entry.name, entry.path))

    # Project subdirs: usr/projects/<name>/<meta>/memory/ (flexible nesting)
    projects_root = os.path.join(USR_DIR, "projects")
    if os.path.isdir(projects_root):
        for proj in sorted(os.scandir(projects_root), key=lambda e: e.name):
            if proj.is_dir(follow_symlinks=True):
                # try direct memory folder
                candidate = os.path.join(proj.path, "memory")
                if os.path.isfile(os.path.join(candidate, "index.faiss")):
                    found.append((f"projects/{proj.name}", candidate))

    return found


def load_faiss_index(db_dir: str) -> list[tuple[str, object, list[float]]]:
    """
    Load a FAISS index without LangChain.

    Returns list of (doc_id, Document, embedding_vector) triples.
    The raw FAISS vectors are reconstructed directly — no API call needed.
    """
    import faiss as faiss_lib

    faiss_path = os.path.join(db_dir, "index.faiss")
    pkl_path = os.path.join(db_dir, "index.pkl")

    if not os.path.isfile(faiss_path) or not os.path.isfile(pkl_path):
        raise FileNotFoundError(f"Missing index.faiss or index.pkl in {db_dir}")

    # Load raw FAISS index (IndexFlatIP stores all vectors → reconstruct works)
    raw_index = faiss_lib.read_index(faiss_path)

    if raw_index.ntotal == 0:
        return []

    # Batch-reconstruct all vectors at once (fast, avoids per-row loop)
    dim = raw_index.d
    all_vecs = np.empty((raw_index.ntotal, dim), dtype=np.float32)
    raw_index.reconstruct_n(0, raw_index.ntotal, all_vecs)

    # Load LangChain FAISS pickle: (index_to_docstore_id, docstore)
    with open(pkl_path, "rb") as fh:
        index_to_docstore_id, docstore = pickle.load(fh)

    doc_dict = getattr(docstore, "_dict", {})

    results: list[tuple[str, object, list[float]]] = []
    for position in range(raw_index.ntotal):
        doc_id = index_to_docstore_id.get(position)
        if doc_id is None or doc_id not in doc_dict:
            continue
        doc = doc_dict[doc_id]
        results.append((doc_id, doc, all_vecs[position].tolist()))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Supabase upsert
# ─────────────────────────────────────────────────────────────────────────────

def get_client():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def upsert_batch(client, subdir: str, rows_data: list, batch_size: int = 100) -> int:
    """Upsert rows to Supabase in batches. Returns count upserted."""
    total = 0
    n = len(rows_data)
    for i in range(0, n, batch_size):
        batch = rows_data[i : i + batch_size]
        rows = [
            {
                "id": doc_id,
                "subdir": subdir,
                "content": doc.page_content,
                "metadata": doc.metadata or {},
                "embedding": embedding,
            }
            for doc_id, doc, embedding in batch
        ]
        client.table(TABLE).upsert(rows).execute()
        total += len(rows)
        # simple progress indicator
        print(f"    {total}/{n} rows upserted...", end="\r", flush=True)
    if n:
        print()  # newline after \r progress
    return total


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  FAISS → Supabase pgvector Migration")
    print("=" * 60)

    # Validate credentials
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("\nERROR: SUPABASE_URL and/or SUPABASE_KEY not found.")
        print(f"  Checked: {os.path.join(USR_DIR, '.env')}")
        print("  Set them in Agent Zero Settings or export them before running.")
        sys.exit(1)

    masked_key = f"{'*' * (len(SUPABASE_KEY) - 4)}{SUPABASE_KEY[-4:]}"
    print(f"\n  URL: {SUPABASE_URL}")
    print(f"  Key: {masked_key}")

    # Discover FAISS indexes
    indexes = find_faiss_indexes()
    if not indexes:
        print(f"\nNo FAISS indexes found under {USR_DIR}/")
        print("Nothing to migrate.")
        sys.exit(0)

    print(f"\nFound {len(indexes)} FAISS index(es):")
    for label, path in indexes:
        kb = os.path.getsize(os.path.join(path, "index.faiss")) // 1024
        print(f"  [{label}]  {path}  ({kb} KB)")

    # Connect to Supabase
    print("\nConnecting to Supabase...")
    try:
        client = get_client()
        client.table(TABLE).select("id").limit(1).execute()  # ping
        print("  Connected.\n")
    except Exception as exc:
        print(f"  ERROR: {exc}")
        print(f"  Make sure table '{TABLE}' exists. Run the SQL from")
        print("  python/helpers/supabase_vector_db.py if not.")
        sys.exit(1)

    grand_total = 0

    for subdir_label, db_path in indexes:
        print(f"Migrating [{subdir_label}]...")
        try:
            rows_data = load_faiss_index(db_path)
        except Exception as exc:
            print(f"  ERROR loading FAISS index: {exc}")
            continue

        if not rows_data:
            print("  Index is empty — skipping.")
            continue

        print(f"  {len(rows_data)} documents loaded from FAISS.")
        try:
            n = upsert_batch(client, subdir_label, rows_data)
            grand_total += n
            print(f"  OK — {n} documents written to Supabase.")
        except Exception as exc:
            print(f"  ERROR upserting: {exc}")

    print()
    print("=" * 60)
    print(f"  Done. {grand_total} total document(s) migrated.")
    print("=" * 60)
    print()
    print("Verify:")
    print("  • Supabase Table Editor → agent_zero_memories should have rows")
    print("  • Agent Zero Settings → External Services → enter URL + key")
    print("  • Restart Agent Zero — it will use Supabase automatically")
    print("  • Ask Angie something she should remember to confirm")
    print()


if __name__ == "__main__":
    main()
