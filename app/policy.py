from pathlib import Path

from fastembed import TextEmbedding
from langchain_core.documents import Document
from langchain_postgres import PGVector

from .config import settings

_POLICY_FILE = Path(__file__).resolve().parent.parent / "data" / "policies.md"
_COLLECTION = "hr_policies"


class _Embeddings:
    """fastembed wrapped in the small interface PGVector expects."""

    def __init__(self, model="BAAI/bge-small-en-v1.5"):
        self._m = TextEmbedding(model_name=model)

    def embed_documents(self, texts):
        return [list(v) for v in self._m.embed(list(texts))]

    def embed_query(self, text):
        return list(next(self._m.embed([text])))


_emb = _Embeddings()
_store = None


def _connect(pre_delete=False):
    return PGVector(embeddings=_emb, collection_name=_COLLECTION,
                    connection=settings.database_url, use_jsonb=True,
                    pre_delete_collection=pre_delete)


def _chunks(text):
    title, buf = "General", []
    for line in text.splitlines():
        if line.startswith("## "):
            if buf:
                yield title, "\n".join(buf).strip()
                buf = []
            title = line[3:].strip()
        elif not line.startswith("# "):
            buf.append(line)
    if buf:
        yield title, "\n".join(buf).strip()


def ingest():
    global _store
    docs = [Document(page_content=f"{t}\n{c}", metadata={"section": t})
            for t, c in _chunks(_POLICY_FILE.read_text()) if c]
    _store = _connect(pre_delete=True)
    _store.add_documents(docs)
    return len(docs)


def search(query, k=3):
    global _store
    if _store is None:
        _store = _connect()
    try:
        return [d.page_content for d in _store.similarity_search(query, k=k)]
    except Exception as ex:
        return [f"(policy search unavailable: {ex})"]
