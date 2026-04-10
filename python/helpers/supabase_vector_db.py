"""Supabase pgvector backend for Agent Zero memory.

Drop-in replacement for the FAISS-backed MyFaiss used in memory.py.
Persists memories in a Supabase table with a pgvector embedding column so
data survives Docker container rebuilds.

Required Supabase setup (run once in the Supabase SQL editor):

    create extension if not exists vector;

    create table if not exists agent_zero_memories (
        id       text primary key,
        subdir   text not null,
        content  text not null,
        metadata jsonb not null default '{}',
        embedding vector(384)   -- change dimension if using a different model
    );

    create index if not exists agent_zero_memories_embedding_idx
        on agent_zero_memories
        using ivfflat (embedding vector_cosine_ops)
        with (lists = 100);

    -- RPC used for similarity search
    create or replace function match_memories(
        query_embedding vector,
        match_subdir    text,
        match_count     int,
        match_threshold float
    )
    returns table (
        id        text,
        content   text,
        metadata  jsonb,
        similarity float
    )
    language sql stable
    as $$
        select
            id,
            content,
            metadata,
            1 - (embedding <=> query_embedding) as similarity
        from agent_zero_memories
        where subdir = match_subdir
          and 1 - (embedding <=> query_embedding) >= match_threshold
        order by embedding <=> query_embedding
        limit match_count;
    $$;
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

TABLE = "agent_zero_memories"


class SupabaseVectorDB:
    """Supabase pgvector-backed vector store matching the MyFaiss interface."""

    def __init__(self, embedder: Embeddings, memory_subdir: str):
        from supabase import create_client
        from python.helpers import dotenv

        url = dotenv.get_dotenv_value(dotenv.KEY_SUPABASE_URL, "")
        key = dotenv.get_dotenv_value(dotenv.KEY_SUPABASE_KEY, "")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be set in usr/.env "
                "or Agent Zero Settings to use the Supabase memory backend."
            )
        self._client = create_client(url, key)
        self._embedder = embedder
        self.memory_subdir = memory_subdir

    # ------------------------------------------------------------------
    # Interface expected by Memory (mirrors MyFaiss)
    # ------------------------------------------------------------------

    def get_by_ids(self, ids: str | Sequence[str]) -> list[Document]:
        if isinstance(ids, str):
            ids = [ids]
        ids = list(ids)
        if not ids:
            return []
        resp = (
            self._client.table(TABLE)
            .select("id, content, metadata")
            .eq("subdir", self.memory_subdir)
            .in_("id", ids)
            .execute()
        )
        return [_row_to_doc(row) for row in (resp.data or [])]

    async def aget_by_ids(self, ids: Sequence[str]) -> list[Document]:
        return self.get_by_ids(list(ids))

    def get_all_docs(self) -> dict[str, Document]:
        resp = (
            self._client.table(TABLE)
            .select("id, content, metadata")
            .eq("subdir", self.memory_subdir)
            .execute()
        )
        return {row["id"]: _row_to_doc(row) for row in (resp.data or [])}

    async def asearch(
        self,
        query: str,
        search_type: str,
        k: int,
        score_threshold: float,
        filter: Callable[[dict], bool] | None = None,
    ) -> list[Document]:
        embedding = self._embedder.embed_query(query)
        # score_threshold arrives in [0,1] (cosine-normalised by Memory)
        # convert back to raw cosine similarity: raw = threshold*2 - 1
        raw_threshold = max(-1.0, score_threshold * 2.0 - 1.0)

        resp = self._client.rpc(
            "match_memories",
            {
                "query_embedding": embedding,
                "match_subdir": self.memory_subdir,
                "match_count": k,
                "match_threshold": raw_threshold,
            },
        ).execute()

        docs: list[Document] = []
        for row in resp.data or []:
            meta = row.get("metadata") or {}
            if filter is None or filter(meta):
                docs.append(Document(page_content=row["content"], metadata=meta))
        return docs

    async def aadd_documents(
        self, documents: list[Document], ids: list[str]
    ) -> list[str]:
        if not documents:
            return []
        texts = [doc.page_content for doc in documents]
        embeddings = self._embedder.embed_documents(texts)
        rows = [
            {
                "id": doc_id,
                "subdir": self.memory_subdir,
                "content": doc.page_content,
                "metadata": doc.metadata,
                "embedding": emb,
            }
            for doc, doc_id, emb in zip(documents, ids, embeddings)
        ]
        self._client.table(TABLE).upsert(rows).execute()
        return ids

    async def adelete(self, ids: list[str]) -> None:
        if not ids:
            return
        self._client.table(TABLE).delete().eq("subdir", self.memory_subdir).in_(
            "id", ids
        ).execute()

    def save_local(self, folder_path: str) -> None:
        """No-op: Supabase persists data automatically."""


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _row_to_doc(row: dict[str, Any]) -> Document:
    meta = row.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    return Document(page_content=row["content"], metadata=meta)


def is_configured() -> bool:
    """Return True if Supabase credentials are present in the environment."""
    from python.helpers import dotenv

    return bool(
        dotenv.get_dotenv_value(dotenv.KEY_SUPABASE_URL)
        and dotenv.get_dotenv_value(dotenv.KEY_SUPABASE_KEY)
    )
