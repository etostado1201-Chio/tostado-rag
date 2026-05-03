"""
rag_engine.py
-------------
Retrieval-Augmented Generation pipeline for Tostado Restaurant Group.

    Embeddings   : sentence-transformers/all-MiniLM-L6-v2  (HuggingFace)
    Vector store : FAISS  (local on disk)
    LLM          : Llama 3.2 3B served by Ollama
    Framework    : LangChain (LCEL)
    Retrieval    : Hybrid — exact ID matching + semantic similarity

Public API:
    engine = RAGEngine()
    engine.build_or_load_index()
    answer = engine.ask("Who is the VP of operations for Stone & Fire?")
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import List

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import ChatOllama
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from .documents import load_all_documents


ROOT       = Path(__file__).resolve().parent.parent
INDEX_DIR  = ROOT / "vector_store"
DATA_DIR   = ROOT / "data"
EMBED_NAME = os.getenv("EMBED_MODEL",  "sentence-transformers/all-MiniLM-L6-v2")
LLM_NAME   = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_URL = os.getenv("OLLAMA_HOST",  "http://localhost:11434")
TOP_K      = int(os.getenv("TOP_K", "8"))

# Words/phrases that signal the user is interested in non-active stores.
# Triggers disabling the default `status = active` filter.
_INCLUDE_INACTIVE_HINTS = (
    "closed", "shut down", "shuttered", "remodeling", "suspended",
    "former", "all stores", "every store", "history", "historical",
    "cerrada", "cerrado", "cerradas", "todas", "antigua",
)


def _build_store_id_regex(data_dir: Path = DATA_DIR) -> "re.Pattern[str]":
    """
    Build the store-ID regex from brands.json so the system stays
    aligned with the live brand list — no code changes needed when a
    brand is added or renamed through the admin console.
    """
    brands_path = data_dir / "brands.json"
    if brands_path.exists():
        brands = json.loads(brands_path.read_text())
        slugs = [b["id"].upper() for b in brands]
    else:
        # Fallback for first-run / test scenarios where brands.json
        # hasn't been written yet.
        slugs = ["GOLDEN_CRISP", "STONE_FIRE", "DAYBREAK", "GARDEN_CRATE"]
    pattern = r"\b(" + "|".join(slugs) + r")-\d{1,4}\b"
    return re.compile(pattern, re.IGNORECASE)


def _build_system_prompt(data_dir: Path = DATA_DIR) -> str:
    brands_path = data_dir / "brands.json"
    if brands_path.exists():
        brands = json.loads(brands_path.read_text())
        active = [b for b in brands if b.get("status", "active") == "active"]
        brand_list = ", ".join(f"{b['name']} ({b['category'].lower()})" for b in active)
    else:
        brand_list = ("Golden Crisp (fried chicken), Stone & Fire (pizza), "
                      "Daybreak Coffee (coffee), Garden Crate (salads)")

    return f"""You are the internal assistant of Tostado Restaurant Group, a holding company that operates these brands: {brand_list}.

You help corporate staff and franchise owners look up store information, manager contacts, district and VP-of-Operations details, vendor accounts (phone and internet), and corporate department contacts.

Rules:
1. Answer using the information present in the provided context. The context contains real records — read it carefully before deciding the answer is not there.
2. If the user mentions a specific store ID (e.g. STONE_FIRE-0007) and you find that exact ID in the context, use that record. Pay attention to ID matching even if other similar stores appear in the context.
3. Some stores may have status "closed" — when answering, mention if a store is closed. Active stores are the default; closed/remodeling/suspended stores only appear when explicitly searched for.
4. Only reply "I don't have that information in my knowledge base." if you have genuinely searched the context and the requested record is not present.
5. Be concise and professional. When you give a phone, email, or login credential, format it clearly on its own line.
6. Treat passwords and account credentials as sensitive — only return them when the user has explicitly asked for them.
7. Never make up store IDs, employee names, phone numbers, or addresses.
"""


USER_PROMPT = """Context:
{context}

Question: {question}

Answer:"""


def _format_docs(docs: List[Document]) -> str:
    return "\n\n---\n\n".join(d.page_content for d in docs)


class RAGEngine:
    def __init__(self) -> None:
        print(f"[RAG] Loading embeddings: {EMBED_NAME}")
        self.embeddings = HuggingFaceEmbeddings(model_name=EMBED_NAME)

        print(f"[RAG] Connecting to Ollama at {OLLAMA_URL} (model {LLM_NAME})")
        self.llm = ChatOllama(model=LLM_NAME, base_url=OLLAMA_URL, temperature=0.1)

        self.vectorstore: FAISS | None = None
        self._all_docs:   list[Document] = []
        self._store_id_re = _build_store_id_regex()
        self.chain                     = None

    # ------------------------------------------------------------------
    # Index lifecycle
    # ------------------------------------------------------------------

    def build_or_load_index(self, force_rebuild: bool = False) -> None:
        # We always need the docs in memory for exact-ID matching, even
        # when we restore the FAISS index from disk.
        self._all_docs = load_all_documents()
        # Refresh the brand-derived regex in case brands.json changed.
        self._store_id_re = _build_store_id_regex()

        if INDEX_DIR.exists() and not force_rebuild:
            print(f"[RAG] Loading FAISS index from {INDEX_DIR}")
            self.vectorstore = FAISS.load_local(
                str(INDEX_DIR),
                self.embeddings,
                allow_dangerous_deserialization=True,
            )
        else:
            print("[RAG] Building FAISS index from scratch...")
            print(f"[RAG] Embedding {len(self._all_docs)} documents...")
            self.vectorstore = FAISS.from_documents(self._all_docs, self.embeddings)
            INDEX_DIR.mkdir(exist_ok=True)
            self.vectorstore.save_local(str(INDEX_DIR))
            print(f"[RAG] Index saved to {INDEX_DIR}")

        self._build_chain()

    def rebuild_index(self) -> None:
        """Called after department admins update the JSON data."""
        self.build_or_load_index(force_rebuild=True)

    # ------------------------------------------------------------------
    # Hybrid retrieval (exact ID + semantic) + status filtering
    # ------------------------------------------------------------------

    def _extract_store_ids(self, text: str) -> list[str]:
        return [m.group(0).upper() for m in self._store_id_re.finditer(text)]

    @staticmethod
    def _wants_inactive(question: str) -> bool:
        """Does the question explicitly ask for non-active records?"""
        q = question.lower()
        return any(hint in q for hint in _INCLUDE_INACTIVE_HINTS)

    @staticmethod
    def _passes_status_filter(doc: Document, include_inactive: bool) -> bool:
        """Closed/suspended docs are excluded unless the question asks for them."""
        if include_inactive:
            return True
        status = (doc.metadata.get("status") or "active").lower()
        # Always keep docs that don't carry a status (vendors, employees, depts).
        return status == "active"

    def _status_matches(self, question: str) -> list[Document]:
        """
        When the user asks for closed/inactive stores, semantic search alone
        is unreliable: 'closed' is a weak signal compared to a brand name in
        the embedding space, so a small number of closed records (e.g. 1 of
        500) gets buried under brand-relevant active records.

        This deterministic pre-filter pulls every store with a non-active
        status straight from metadata, ensuring the LLM at least sees them.
        """
        if not self._wants_inactive(question):
            return []
        return [d for d in self._all_docs
                if d.metadata.get("type") == "store"
                and (d.metadata.get("status") or "active") != "active"]

    def _exact_id_matches(self, question: str, include_inactive: bool) -> list[Document]:
        """
        Find every doc whose metadata references a store ID mentioned
        in the question.

        Important: when the user names a specific store ID, we return
        that record *regardless of its status*. They asked for that
        store by name — hiding it because it's closed would make the
        bot lie ("I don't have that information") about a record we
        clearly have. The LLM is instructed to mention closed status
        when it answers.
        """
        ids = self._extract_store_ids(question)
        if not ids:
            return []

        matches: list[Document] = []
        for d in self._all_docs:
            sid = str(d.metadata.get("store_id", "")).upper()
            if sid and sid in ids:
                matches.append(d)
        return matches

    def _hybrid_retrieve(self, question: str) -> list[Document]:
        """
        Three-source retrieval, in priority order:
          1. Exact-ID matches  — if user names a specific store_id, always include it
          2. Status matches    — if user asks for "closed" stores, include all of them
          3. FAISS semantic    — fill the rest with semantic similarity, status-filtered

        Then dedupe while preserving order.
        """
        include_inactive = self._wants_inactive(question)

        exact  = self._exact_id_matches(question, include_inactive)
        status = self._status_matches(question)

        # Over-fetch from FAISS so we still have enough docs after filtering.
        semantic_raw = self.vectorstore.similarity_search(question, k=TOP_K * 2)
        semantic = [d for d in semantic_raw
                    if self._passes_status_filter(d, include_inactive)][:TOP_K]

        seen: set[str] = set()
        ordered: list[Document] = []
        for d in exact + status + semantic:
            key = d.page_content[:120]
            if key in seen:
                continue
            seen.add(key)
            ordered.append(d)
        return ordered

    # ------------------------------------------------------------------
    # Chain construction (LangChain LCEL)
    # ------------------------------------------------------------------

    def _build_chain(self) -> None:
        prompt = ChatPromptTemplate.from_messages([
            ("system", _build_system_prompt()),
            ("user",   USER_PROMPT),
        ])
        self.chain = prompt | self.llm | StrOutputParser()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def ask(self, question: str) -> dict:
        if self.chain is None:
            raise RuntimeError("Index not built yet — call build_or_load_index() first.")

        sources = self._hybrid_retrieve(question)
        context = _format_docs(sources)

        answer = self.chain.invoke({"context": context, "question": question})

        return {
            "answer":  answer,
            "sources": [
                {"content": d.page_content, "metadata": d.metadata}
                for d in sources
            ],
        }
