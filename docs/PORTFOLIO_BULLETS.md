# Portfolio bullets — ready to paste

Pick the version that fits the space you have. All three describe the
same project, just at different lengths and emphases.

---

## Long form (CV / résumé bullet group, ~5 lines)

**Tostado RAG — Internal AI Assistant** · _Personal project_ · 2026
*Python · LangChain · FAISS · HuggingFace · Flask · Ollama · Docker*
🔗 [github.com/etostado1201-Chio/tostado-rag](https://github.com/etostado1201-Chio/tostado-rag)

- Built an end-to-end retrieval-augmented chatbot over 1,638 internal
  records (500 stores, 1,000 vendor accounts, 4 brands, departments
  and employees of a fictional restaurant holding company), serving
  answers in under 3 s on commodity hardware.
- Designed the RAG pipeline with HuggingFace `all-MiniLM-L6-v2`
  embeddings, FAISS top-k retrieval, and Llama 3.2:3b on Ollama —
  measured retrieval **recall@6 ≥ 90%** and **MRR ≥ 0.85** on a
  hand-curated 36-question eval set, then debugged and fixed three
  real retrieval bugs documented in the repo.
- Implemented **hybrid retrieval** (exact-ID + metadata pre-filter +
  semantic) after discovering that embedding-only search misses
  alphanumeric IDs and underweights categorical fields like
  `status: closed`.
- Shipped voice I/O (HuggingFace Whisper STT + browser-native TTS),
  per-department admin auth (bcrypt + JWT), full CRUD admin console
  with hybrid form (visual + JSON modes), atomic store creation
  (store + 2 vendor accounts in one operation), soft-delete with
  audit trail, and live FAISS reindexing on every approved data update.
- Production-minded engineering: **97-test pytest suite** running on
  GitHub Actions across Python 3.10 / 3.11 / 3.12, structured JSON
  logging, in-process metrics endpoint with latency percentiles,
  Docker Compose stack, and a `create_app()` factory pattern for
  hermetic tests with mock-injected RAG engine.
- Released under MIT for franchise-owner reuse and as a portfolio
  artifact for the IBM *Building Generative AI-Powered Applications*
  course.

---

## Medium form (LinkedIn project, ~3 lines)

**Tostado RAG — Internal AI Assistant** *(Python · LangChain · FAISS · Ollama)*

End-to-end RAG chatbot over 1,638 synthetic enterprise records.
HuggingFace embeddings + FAISS hybrid retrieval (exact-ID +
metadata + semantic) + Llama 3.2:3b via Ollama. Voice I/O,
per-department admin auth, full CRUD console with atomic store
creation, soft-delete with audit trail, FAISS reindexing on every
data update. **97 tests** running on CI matrix, Docker Compose
stack. Retrieval recall@6 ≥ 90% measured on a hand-curated eval
set with a custom evaluation harness. MIT-licensed.

🔗 [github.com/etostado1201-Chio/tostado-rag](https://github.com/etostado1201-Chio/tostado-rag)

---

## Short form (one-liner for a cover letter)

> Built and open-sourced a retrieval-augmented chatbot covering 500
> stores and 1,000 vendor accounts, with measured **90%+ recall@6**,
> hybrid retrieval (exact-ID + metadata + semantic), voice I/O,
> JWT-based admin updates, and a 97-test CI suite — all on
> open-source local infra (LangChain · FAISS · Llama 3.2:3b on Ollama).
> Repo: [github.com/etostado1201-Chio/tostado-rag](https://github.com/etostado1201-Chio/tostado-rag)

---

## Skills extracted (paste these into the "Skills" section)

```
Generative AI:    RAG, LLMs, embeddings, vector search, prompt engineering,
                  hybrid retrieval, metadata pre-filtering
Frameworks:       LangChain (LCEL), HuggingFace transformers, sentence-transformers
LLM serving:      Ollama, Llama 3.2, prompt templates with LCEL
Vector stores:    FAISS (in-process, persisted to disk)
Speech I/O:       Whisper STT, browser SpeechSynthesis TTS
Backend:          Python, Flask, Flask-CORS, factory pattern
Auth & security:  bcrypt password hashing, JWT (PyJWT), per-route guards,
                  soft-delete with referential integrity
Frontend:         HTML, CSS, vanilla JavaScript, MediaRecorder API,
                  hybrid forms (visual + JSON modes)
Testing:          pytest, fixtures, mock-injected test client (97 tests)
DevOps:           Docker, Docker Compose, GitHub Actions, structured JSON logging
Evaluation:       recall@k, MRR, latency percentiles, per-category breakdowns
```

---

## Tips for using these bullets

1. **Match the role.** If the JD mentions "vector databases" → keep the
   FAISS bullet front-and-centre. If it mentions "evaluation" → lead
   with the recall@6 line.
2. **Always include a number.** "90%+ recall@6" or "60 tests" or
   "1,631 documents" beats any adjective.
3. **Mention what you decided, not what you used.** "Chose FAISS over
   Pinecone because…" is a stronger signal than "used FAISS".
4. **Link the repo.** A reviewer can read 10 lines of your README in
   30 seconds and decide you're worth a screen. Make sure the
   reviewer-visible state is the README's first 30 lines.

---

## Talking points for behavioural / technical interviews

### "Tell me about a hard bug you've debugged"

The retrieval pipeline had three distinct bugs that all came from the
same root cause: `all-MiniLM-L6-v2` is a general-purpose embedding
model, and it doesn't weight different signals the way a human reader
would.

1. **Alphanumeric store IDs** like `STONE_FIRE-0007` are rare tokens.
   The model couldn't surface the exact record when the user named
   it specifically — semantic neighbours of the same brand ranked
   higher. Fix: regex out store IDs from the question and prepend
   exact metadata matches before the FAISS top-k.

2. **Status filter clobbered exact matches**. When I added soft-delete
   with a `status: closed` field, my filter excluded closed records
   from default retrieval — including the exact-ID matches. So
   "what's the status of STONE_FIRE-0002" (which IS closed) sent
   the LLM a context full of *other* Stone & Fire stores, and the
   LLM happily hallucinated "is active". Fix: never status-filter
   exact-ID matches; trust the user's intent when they name a
   specific record.

3. **Closed stores buried by semantic search**. "Show me closed
   stores" still failed because the word "closed" carries far less
   weight than "Stone & Fire" in the embedding space. With only 1
   closed of 500, FAISS top-8 was always 8 active brand matches.
   Fix: metadata pre-filtering. When the question contains hints
   like "closed", "shut down", "cerrada", run a direct filter over
   `metadata.status` and inject those docs at the front of the
   context, ahead of the semantic results.

The deeper lesson: **embeddings alone are insufficient when queries
depend on categorical fields**. Production RAG systems combine three
signals — exact match, metadata pre-filter, semantic similarity —
and the priority order matters. This is the standard "hybrid retrieval"
pattern from systems like Vespa, Pinecone metadata filters, and the
ReACT/RAG papers.

### "What's the weakest part of the project?"

Be honest — interviewers can smell pretence:

- **No end-to-end answer-quality eval**. Retrieval-only metrics catch
  ~70% of bugs but miss "right docs, wrong answer". Adding `ragas`
  or LLM-as-judge is in `Future work`.
- **Single Ollama process** is the obvious bottleneck under any real
  concurrent load.
- **All-or-nothing admin scopes** — currently any logged-in admin
  can patch any dataset. Per-department write scopes would be the
  right next step.
- **Status-trigger heuristic is brittle** — relies on a hand-curated
  word list. A proper solution would be a small classifier (or just
  a tool-using LLM) that detects "user intent: include inactive".

---

## LinkedIn announcement post (ready to paste)

When you're ready to share the project, paste this in a new LinkedIn post.
Edit the first line to match your voice — the rest is fine as-is.

> 🚀 Just open-sourced my first AI Engineering portfolio project: **Tostado RAG**.
>
> It's an internal assistant for a fictional restaurant group with 500 stores across 4 brands. Built end-to-end with:
>
> 🧠 **LangChain + FAISS + Ollama Llama 3.2:3b** for retrieval-augmented generation
> 🎤 **HuggingFace Whisper STT + browser-native TTS** for voice I/O
> 🔐 **JWT + bcrypt** auth with per-department admin console (full CRUD)
> 📊 **Hand-curated eval set** measuring retrieval recall@k and MRR
> ✅ **97 tests** running on GitHub Actions across Python 3.10 / 3.11 / 3.12
> 🐳 **Docker Compose** stack with Ollama + Flask
>
> The most interesting part: I documented 3 real RAG retrieval bugs I encountered while building it, plus how I fixed them. Turns out `all-MiniLM-L6-v2` doesn't weight categorical fields like `status: closed` the way you'd hope, so you need **hybrid retrieval** (exact match + metadata pre-filter + semantic similarity).
>
> Built as my capstone for IBM's *Building Generative AI-Powered Applications with Python* course. MIT-licensed and ready to fork.
>
> 🔗 https://github.com/etostado1201-Chio/tostado-rag
>
> #GenerativeAI #RAG #LangChain #Python #AIEngineering #OpenSource #HuggingFace #Ollama

---

## GitHub profile bio (one-liner)

Update your GitHub profile bio at <https://github.com/settings/profile>:

> Aspiring AI Engineer · Building with LangChain, FAISS, and HuggingFace ·
> IBM Generative AI student · Currently shipping
> [tostado-rag](https://github.com/etostado1201-Chio/tostado-rag)

---

## GitHub profile README (optional but high-impact)

If you want your profile page itself (https://github.com/etostado1201-Chio)
to look polished, create a special repo with the same name as your username
— GitHub will use its README as your profile homepage.

```bash
# Create the magic repo
mkdir etostado1201-Chio && cd etostado1201-Chio
```

Then add a `README.md` like:

```markdown
### Hi there 👋

I'm Eduardo (Chio) Tostado — building toward a career as an AI Engineer.

**Currently learning**
- IBM *Building Generative AI-Powered Applications with Python* on Coursera
- Production RAG patterns: hybrid retrieval, evaluation harnesses, observability

**Recent project**
- 🚀 [tostado-rag](https://github.com/etostado1201-Chio/tostado-rag) —
  internal AI assistant over 500 stores · LangChain + FAISS + Ollama ·
  voice I/O · 97 tests · 90%+ recall@6

**Open to**
Entry-level AI Engineer / ML Engineer roles · happy to collaborate on
open-source RAG and LLM tooling.

📫 Reach me at [your-email] · [LinkedIn](https://linkedin.com/in/your-handle)
```