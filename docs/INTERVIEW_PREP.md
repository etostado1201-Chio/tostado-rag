# Interview prep — using this project as a portfolio anchor

This document is a personal cheat-sheet for talking about Tostado RAG in
an interview. Every answer is grounded in code that actually lives in
this repo, so you can point at lines if you need to.

The goal is not to recite memorised answers — it's to have one project
you understand deeply enough that you can riff on it.

---

## How to introduce the project (60-second pitch)

> "I built an internal RAG-powered assistant for a fictional restaurant
> holding company that runs four fast-food brands and 500 stores. It
> answers questions about store managers, vendor accounts, and corporate
> departments — all retrieved from a local FAISS index of synthetic data
> generated with Faker.
>
> The stack is Python + Flask on the backend, vanilla HTML/CSS/JS on the
> frontend, LangChain orchestrating retrieval, HuggingFace
> `all-MiniLM-L6-v2` for embeddings, and Llama 3.2:3b served by Ollama
> for the LLM. I added a HuggingFace Whisper STT route and browser-native
> TTS so users can also talk to it.
>
> Operationally it ships with 60 pytest tests, a GitHub Actions CI
> matrix on Python 3.10/3.11/3.12, a docker-compose setup that brings up
> Ollama and the app together, and a retrieval-eval harness with
> recall@k and MRR so I can quantify quality changes."

That's roughly 90 seconds spoken. Cut the operational bullet for a
shorter version.

---

## Technical questions you should expect

### 1. "Walk me through what happens when a user asks a question."

1. Browser POSTs `{"message": "Who manages GOLDEN_CRISP-0001?"}` to
   `/api/chat`.
2. Flask passes the question to `RAGEngine.ask`. The retriever embeds
   the question with `all-MiniLM-L6-v2` (384 dims).
3. FAISS does a cosine-similarity search over 1,631 pre-embedded
   passages and returns the top 6.
4. Those 6 passages are concatenated into a prompt with a strict system
   message ("answer only from the context, refuse otherwise").
5. The prompt goes to `llama3.2:3b` running on Ollama. Token-by-token
   generation, ~1–3 s on CPU.
6. The answer plus the 6 source passages plus 2–3 rule-based follow-up
   suggestions are returned as JSON.
7. Frontend renders the answer, an expandable `<details>` block of
   sources, and clickable follow-up chips. If "Voice replies" is on,
   the browser's `SpeechSynthesis` API reads the answer aloud.

### 2. "Why FAISS and not Pinecone / Weaviate / pgvector?"

- Single-tenant internal tool, ~1.6k vectors. FAISS in-process is the
  honest choice; remote vector DBs would add latency and ops overhead
  for zero benefit.
- The whole index is a few MB and rebuilds in seconds, so the
  "rebuild on admin update" flow stays simple — no eventual-consistency
  reasoning required.
- If the data grew to 10M+ vectors or needed multi-region replication,
  I'd reach for pgvector or Pinecone — see `docs/ARCHITECTURE.md`
  Future Work.

### 3. "Why `all-MiniLM-L6-v2`?"

- 384-dim, ~80 MB, fast on CPU — embeds 1,631 docs in ~4 s on the
  laptop I built this on.
- Strong baseline for English semantic similarity: it's the workhorse
  default of the `sentence-transformers` library.
- Eval recall@6 is about 90%+ on the manually-curated eval set
  (see `docs/eval_results.md`). For a CRUD-lookup style RAG,
  that's enough to be useful without paying API fees.
- If I needed multilingual support I'd swap to
  `paraphrase-multilingual-MiniLM-L12-v2`. If I needed higher quality
  English I'd try `bge-base-en-v1.5`. Both are drop-in.

### 4. "Why `llama3.2:3b` instead of GPT-4 or Claude?"

- Cost. The user is a franchise owner with 500 stores, not a Fortune
  500. A 3B model running locally costs $0/query.
- Privacy. Vendor logins and admin contacts never leave the machine.
- The task is **answering from retrieved context**, not creative
  reasoning. A 3B model is fine when you just need it to summarize what
  the retriever already found. The retriever is the brain; the LLM is
  the mouth.
- The architecture is LLM-agnostic — `LangChain.ChatOllama` swaps
  cleanly for `ChatAnthropic` or `ChatOpenAI` if a customer is willing
  to pay for that quality.

### 5. "How do you evaluate the retrieval system?"

- I built a hand-curated eval dataset of 36 questions across 3 categories
  (stores, vendors, departments) — `scripts/eval_dataset.py`.
- Each question is paired with the document the retriever *should*
  return.
- `scripts/evaluate_rag.py` computes **recall@1, recall@3, recall@6**
  and **MRR** (mean reciprocal rank).
- It also reports retrieval p50/p95 latency, and per-category
  breakdowns so I can tell if e.g. vendor accounts retrieve worse than
  stores.
- The script's exit code is 0 only if recall@6 ≥ 0.85, so it can be
  wired into CI to catch retrieval regressions when I change the
  embedding model or the prompt.

The deliberate gap I'm honest about: **answer quality is not measured
end-to-end yet.** Real evaluation would compare LLM answers against
expected answers using something like `ragas` or LLM-as-judge.
That's in `Future work` because it requires a paid LLM to grade
fairly, and I wanted the project free to clone.

### 6. "How would you scale this to 100,000 stores?"

In rough order of impact:

1. **Storage** — JSON files don't scale. Move to Postgres with a
   change-data-capture stream that re-embeds only changed rows.
2. **Vector store** — swap FAISS in-process for FAISS-on-disk or
   pgvector with HNSW indexes. Avoid full reindex on writes.
3. **LLM serving** — Ollama is single-process. Move to a hosted
   inference service (vLLM behind an LB, or a managed API) so the
   Flask app can scale horizontally without each replica needing its
   own GPU.
4. **Caching** — same store gets queried by ~5 people per day; a small
   LRU on `(question, top-6-doc-ids)` would cut LLM calls a lot.
5. **Auth** — JWT in a cookie is fine for a single tenant; for 100k
   stores in multiple franchise groups you'd want OIDC + per-tenant
   isolation.

### 7. "What did you learn that surprised you?"

Pick one — practice saying it out loud, not reading it:

- **Browser-native TTS is great**. I almost reached for HuggingFace
  speecht5 server-side and would have wasted a day on it. The
  `SpeechSynthesis` API works on every modern browser, sounds fine,
  and adds zero latency or install footprint.
- **`from_documents` is misleadingly slow**. It re-embeds everything
  on every call. I had to add `build_or_load_index` with disk
  persistence — saved 30s on every restart.
- **Rule-based follow-ups beat LLM follow-ups for this task**. I
  almost added a second LLM call to generate "did you mean..."
  suggestions, but the metadata I already have is sharper than
  anything a 3B model would invent. Sometimes the right answer is no
  ML.

### 8. "What's the weakest part of the project?"

Be honest — interviewers can smell when you're pretending it's
perfect. Pick one or two real ones:

- **No end-to-end answer-quality eval.** Retrieval-only.
- **Single-process Ollama** is the obvious bottleneck under any
  realistic concurrent load.
- **Admin update is shallow `dict.update`** — nested fields aren't
  patchable. A real version would support JSON Patch (RFC 6902).
- **No streaming**. The user waits for the full answer; SSE would
  feel much faster.

---

## Foundational knowledge that sits underneath

The interviewer may ask about RAG concepts in the abstract, not about
this project specifically. Be ready for:

- **What is an embedding?** A learned dense vector representation of
  text where semantically similar inputs end up close together by
  cosine similarity.
- **What is RAG and why use it?** Retrieval-Augmented Generation:
  augment an LLM's prompt with relevant facts pulled from a corpus.
  Cheaper than fine-tuning, more current, easier to audit (you see
  which doc was used).
- **Why chunk documents?** Embedding quality drops on very long inputs,
  and the LLM context window is finite. (For this project I didn't
  chunk — every record is short and self-contained, which kept
  retrieval crisp.)
- **What is hallucination and how do you mitigate it?** The LLM
  generating plausible-but-false content. Mitigations: strict system
  prompt ("answer only from context"), low temperature, surface
  sources in the UI, refuse explicitly when context is empty.
- **What is the difference between `top-k` and a re-ranker?** `top-k`
  retrieves k candidates by raw similarity. A re-ranker (e.g.
  `bge-reranker-base`) re-orders those k with a slower cross-encoder
  for higher precision. Worth it on noisy corpora; overkill here.

---

## Things to absolutely avoid

- Don't claim things the project doesn't do (e.g. "production-grade",
  "scalable to millions"). It's a portfolio piece — be precise about
  what is and isn't there.
- Don't say "I used AI to help build this" without specifics. Say
  *what you decided* and *why* — that's the engineering signal.
- Don't pad. If you don't know something, say "I haven't worked with
  that yet — here's the closest thing I have."
