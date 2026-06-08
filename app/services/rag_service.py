"""Local RAG over news headlines and seeded filing excerpts."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class RagService:
    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.rag_enabled
        self.top_k = settings.rag_top_k
        self.persist_dir = Path(settings.chroma_persist_dir)
        self.filings_dir = Path("data/filings")
        self._collection = None
        self._embedder = None
        self._memory_corpus: list[dict[str, Any]] = []
        self._bootstrap_corpus()

    def ingest_news(self, *, ticker: str, articles: list[dict[str, Any]]) -> None:
        if not self.enabled:
            return
        normalized = ticker.strip().upper()
        for article in articles:
            text = f"{article.get('title', '')}\n{article.get('summary', '')}".strip()
            if not text:
                continue
            doc_id = f"news:{normalized}:{hash(text) & 0xFFFFFFFF:08x}"
            metadata = {
                "ticker": normalized,
                "source": str(article.get("source") or "news"),
                "url": str(article.get("url") or ""),
                "doc_type": "news",
            }
            self._upsert(doc_id=doc_id, text=text, metadata=metadata)

    def retrieve(self, *, ticker: str, query: str) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        normalized = ticker.strip().upper()
        scoped_query = f"{normalized} {query}".strip()
        chroma_hits = self._retrieve_chroma(scoped_query, ticker=normalized)
        if chroma_hits:
            return chroma_hits[: self.top_k]
        return self._retrieve_memory(scoped_query, ticker=normalized)[: self.top_k]

    def ask(
        self,
        *,
        ticker: str,
        question: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        chunks = self.retrieve(ticker=ticker, query=question)
        confidence = "low"
        if len(chunks) >= 3:
            confidence = "high"
        elif len(chunks) >= 1:
            confidence = "medium"

        if not chunks:
            return {
                "answer": "Insufficient retrieved evidence to answer confidently. Try analyzing the ticker first.",
                "citations": [],
                "retrieval_confidence": "low",
            }

        settings = get_settings()
        if settings.llm_synthesis_enabled:
            try:
                return self._ask_with_llm(ticker=ticker, question=question, chunks=chunks, context=context or {})
            except Exception as exc:
                logger.warning("RAG LLM answer failed: %s", exc)

        citations = [
            {
                "source": chunk.get("source", "unknown"),
                "excerpt": chunk.get("text", "")[:280],
                "url": chunk.get("url", ""),
            }
            for chunk in chunks
        ]
        excerpt = citations[0]["excerpt"] if citations else ""
        return {
            "answer": (
                f"Based on retrieved evidence for {ticker.upper()}: {excerpt} "
                f"(and {max(0, len(citations) - 1)} additional source(s))."
            ),
            "citations": citations,
            "retrieval_confidence": confidence,
        }

    def _ask_with_llm(
        self,
        *,
        ticker: str,
        question: str,
        chunks: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        from app.services.ollama_client import get_ollama_client
        from app.services.structured_output import parse_ask_response

        prompt = json.dumps(
            {
                "ticker": ticker,
                "question": question,
                "retrieved_chunks": chunks,
                "analysis_context": context,
            },
            default=str,
        )
        system = (
            "Answer the user's finance research question using only retrieved chunks and provided context. "
            "If evidence is weak, say so. Return JSON with keys: answer, citations "
            "(list of {source, excerpt, url}), retrieval_confidence (high|medium|low). "
            "Do not provide investment advice or price targets."
        )
        raw_text = get_ollama_client().chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            format_json=True,
        )
        parsed = json.loads(raw_text)
        return parse_ask_response(parsed)

    def _bootstrap_corpus(self) -> None:
        self.filings_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.filings_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            ticker = str(payload.get("ticker", "")).strip().upper()
            for section in payload.get("sections", []):
                text = str(section.get("text", "")).strip()
                if not text:
                    continue
                doc_id = f"filing:{ticker}:{section.get('name', 'section')}"
                metadata = {
                    "ticker": ticker,
                    "source": str(section.get("source") or "sec_filing"),
                    "url": str(section.get("url") or ""),
                    "doc_type": "filing",
                }
                self._upsert(doc_id=doc_id, text=text, metadata=metadata)

    def _upsert(self, *, doc_id: str, text: str, metadata: dict[str, Any]) -> None:
        self._memory_corpus.append({"id": doc_id, "text": text, **metadata})
        collection = self._get_collection()
        if collection is None:
            return
        try:
            embedding = self._embed(text)
            collection.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata],
                embeddings=[embedding],
            )
        except Exception as exc:
            logger.debug("Chroma upsert skipped for %s: %s", doc_id, exc)

    def _retrieve_chroma(self, query: str, *, ticker: str) -> list[dict[str, Any]]:
        collection = self._get_collection()
        if collection is None:
            return []
        try:
            embedding = self._embed(query)
            result = collection.query(
                query_embeddings=[embedding],
                n_results=self.top_k * 2,
                where={"ticker": ticker},
            )
        except Exception as exc:
            logger.debug("Chroma query failed: %s", exc)
            return []

        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        hits: list[dict[str, Any]] = []
        for doc, meta in zip(documents, metadatas):
            if not doc:
                continue
            hits.append(
                {
                    "text": doc,
                    "source": (meta or {}).get("source", "unknown"),
                    "url": (meta or {}).get("url", ""),
                    "doc_type": (meta or {}).get("doc_type", "unknown"),
                }
            )
        return hits

    def _retrieve_memory(self, query: str, *, ticker: str) -> list[dict[str, Any]]:
        query_tokens = _tokenize(query)
        scored: list[tuple[float, dict[str, Any]]] = []
        for item in self._memory_corpus:
            if item.get("ticker") != ticker:
                continue
            doc_tokens = _tokenize(item.get("text", ""))
            if not doc_tokens:
                continue
            overlap = len(query_tokens & doc_tokens) / max(1, len(query_tokens))
            if overlap <= 0:
                continue
            scored.append(
                (
                    overlap,
                    {
                        "text": item.get("text", ""),
                        "source": item.get("source", "unknown"),
                        "url": item.get("url", ""),
                        "doc_type": item.get("doc_type", "unknown"),
                    },
                )
            )
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored]

    def _get_collection(self):
        if not self.enabled:
            return None
        if self._collection is not None:
            return self._collection
        try:
            import chromadb  # type: ignore[import-untyped]

            client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._collection = client.get_or_create_collection(name="financial_research")
            return self._collection
        except Exception as exc:
            logger.warning("Chroma unavailable, using memory retrieval: %s", exc)
            return None

    def _embed(self, text: str) -> list[float]:
        model = self._get_embedder()
        if model is None:
            raise RuntimeError("Embedder unavailable")
        vector = model.encode(text)
        return vector.tolist()

    def _get_embedder(self):
        if self._embedder is not None:
            return self._embedder
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

            self._embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            return self._embedder
        except Exception as exc:
            logger.warning("SentenceTransformer unavailable: %s", exc)
            return None


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(text.lower()))


@lru_cache
def get_rag_service() -> RagService:
    return RagService()
