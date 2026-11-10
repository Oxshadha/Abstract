# Research: Enterprise "Chat with your Paper" Systems

> ⚠️ **Background material only, not a decision record.** It surveys options, some of which were later rejected (e.g. SQLite + Chroma, LangChain, Render/Railway, FastAPI BackgroundTasks). **What we actually build is defined in [`decisions.md`](decisions.md)**; see its "Superseded options" table.

Background research for the **Research Assistant for PDFs** task (upload one paper → structured summary → grounded Q&A).
It looks at what existing tools do, how they are built, and what we should borrow.

---

## 1. Landscape: who does this already, and what they are known for

| Product | Core strength | Features worth borrowing |
|---|---|---|
| **SciSpace (Copilot)** | Reading a single paper | Highlight text, math or a table and click "Explain". Preset prompts ("Summarize methodology"). Follow-up questions. Explanations at different levels. |
| **Elicit** | Structured extraction | Results as **columns** (Methodology, Sample size, Results), each cell backed by a **sentence-level citation quote**. This is the closest match to our "predefined template". |
| **NotebookLM** (Google) | Grounded multi-document Q&A | **Inline citation chips** that jump to and highlight the source passage. Suggested questions. Audio overview, mind maps, flashcards and quizzes. Says so when the answer is not in the sources. |
| **Adobe Acrobat AI Assistant** | Enterprise PDF | Generative summary with **attributions** that link to exact spots in the PDF. Side panel next to the document. Suggested questions. |
| **Semantic Scholar Semantic Reader** | Reading aids | TLDR, highlights of key sentences ("Goal / Method / Result"), citation cards when hovering a reference. |
| **Scholarcy** | Summary cards | Summary flashcards split into sections (key concepts, findings, limitations) and extraction of references. |
| **ChatPDF / Humata / AskYourPDF** | Simple chat | Drag-and-drop, chat in seconds, page-number citations. This is the baseline bar. |
| **alphaXiv / Consensus** | Discovery | Links to related papers. Consensus meter. |

**What the best tools share:** (1) a **split view** with the PDF on one side and AI on the other, (2) **every claim is cited and clickable**, (3) **it streams and never blocks** the user, (4) **suggested questions** to get past the blank chat box, (5) it says clearly when something is **not in the paper**.

---

## 2. Reference architecture

```
                 ┌────────────── React SPA ───────────────┐
                 │ Upload │ PDF viewer │ Summary │ Chat    │
                 └───┬─────────▲─────────▲─────────▲──────┘
            POST /papers   GET /file   SSE /summary  SSE /chat
                 │                                   │
┌────────────────▼──────────── API (FastAPI) ────────┴──────────────────┐
│ validate → sha256 dedupe → store file → enqueue job → 202 + paper_id   │
└────────────────┬──────────────────────────────────────────────────────┘
                 ▼  background worker (job status: parsing→indexing→summarizing→ready)
  ┌─────────── INGESTION ───────────┐   ┌──────── SUMMARY ────────┐
  │ parse (text+layout+page/bbox)   │   │ full paper (fits in a    │
  │ → detect sections (Abstract,    │──▶│ long context window) →   │
  │   Methods…), drop References    │   │ structured JSON schema   │
  │ → section-aware chunks + context│   │ (5 sections + citations) │
  │ → embed → vector + BM25 index   │   └──────────────────────────┘
  └─────────────────────────────────┘
                 ▼
  ┌──────────────────────── Q&A (RAG) ───────────────────────────┐
  │ history-aware query rewrite (small model)                     │
  │ → route: summary-level? / specific? / out-of-scope?           │
  │ → hybrid retrieve (vector + BM25, RRF fusion, top ~30)        │
  │ → rerank → top 5–8 chunks (with section + page)               │
  │ → generate with numbered sources [1][2] → stream tokens (SSE) │
  │ → citations map to {page, bbox} → viewer highlights them      │
  └───────────────────────────────────────────────────────────────┘
```

### Key insight: one paper fits in the context window
A typical paper is 8–30 pages, roughly **10k–40k tokens**, so it fits in current long-context models.
- **Summary:** give the model the *whole* parsed paper. Do not use map-reduce, which loses information across chunks.
- **Q&A:** there are three options. **(a) pure RAG** shows retrieval engineering, which the brief invites. **(b) full document + prompt caching** often gives better answers on a single paper and caching makes the cost reasonable. **(c) a hybrid**: RAG by default, with the full document or summary for questions about the whole paper ("what's the main contribution?"). Picking one is a core design decision.

---

## 3. Pipeline in detail, with tools

### 3.1 Parsing
| Tool | Use |
|---|---|
| **PyMuPDF / pymupdf4llm** | Fast (milliseconds per page), no ML models, gives page numbers and bounding boxes. Good default for PDFs with a native text layer. |
| **GROBID** (Docker) | Built for scientific papers: outputs TEI-XML with **title, authors, abstract, sections and references**, which maps almost exactly to our template. Needs a heavy container. |
| **Docling** (IBM) / **Marker** | Layout-aware conversion to Markdown, with good tables and multi-column handling. Slower, heavier dependencies. |
| **OCRmyPDF / Tesseract** | Scanned PDFs with no text layer. |
| **Vision LLM fallback** | Figures, tables, scanned pages. Costly, so use only on demand. |

### 3.2 Chunking
- **Section-aware**: split by the detected headings first, then by about 500–800 tokens with roughly 10–15% overlap.
- Keep metadata on each chunk: `section`, `page_start/end`, `bbox`, `chunk_index`.
- **Contextual retrieval**: put a short header before each chunk ("Paper: X. Section: 3.2 Training setup."), or a one-line LLM-written context. Anthropic reports large drops in retrieval failures with this approach.
- Index **tables and figure captions as their own chunks**. **Leave out the References section** from retrieval, because it pollutes results.

### 3.3 Retrieval
- **Embeddings:** an API model (OpenAI `text-embedding-3-small`, Voyage, Gemini) or a local one (`bge-small`/`bge-m3`, `nomic-embed`) for zero cost.
- **Vector store:** **pgvector** (one Postgres instance for metadata, vectors and full-text search), **Chroma/LanceDB** (embedded, no infrastructure), Qdrant (scale).
- **Hybrid:** vector search plus BM25 (Postgres `tsvector` or `rank_bm25`), merged with **Reciprocal Rank Fusion**. Dense-only search misses exact terms like "ResNet-50", "Table 3" or "p < 0.05".
- **Rerank:** Cohere Rerank, Voyage rerank, or local `bge-reranker`. Retrieve about 30 candidates, keep 5–8.
- **Query rewriting:** turn "what about their second experiment?" into a standalone query using chat history.

### 3.4 Generation
- **Structured output** (JSON schema / Pydantic) for the summary: `{title, authors[], abstract, problem_statement, methodology, key_results[], conclusion}`, each with `citations: [{page, quote}]`.
- **Grounding prompt:** answer only from the sources, cite `[n]`, and reply "not found in the paper" when it isn't there.
- **Treat PDF text as untrusted data** (prompt-injection defence): put it in delimiters and never follow instructions found inside it.
- **Streaming** over SSE for both the summary (section by section) and chat (token by token).

---

## 4. Edge cases to handle

**Input**
- Not a PDF (renamed `.exe`): check magic bytes `%PDF`, not just the extension.
- Encrypted or password-protected PDF, or a corrupt/truncated file.
- **Scanned PDF with no text layer**: detect a low character count per page, then OCR or show a clear error.
- Very large files (200+ pages or 50MB+): enforce limits and truncate or summarize hierarchically.
- **Not a research paper** (invoice, slides): detect it and warn, but still summarize as well as possible.
- Non-English papers, two-column layouts, ligatures (ﬁ), hyphenation across lines, headers and footers repeated on every page.
- Missing sections (no abstract, "Results and Discussion" merged): the template must say "Not explicitly stated" and **must not hallucinate**.
- Heavy equations (LaTeX), with information that exists only in figures or tables.
- The same file uploaded twice: deduplicate by sha256 and reuse the existing summary and index.
- Malicious PDFs (embedded JavaScript, decompression bombs): parse in a worker process with timeouts.

**Q&A**
- Out-of-scope question ("what's the weather?") or a question whose answer isn't in the paper.
- Follow-ups that need context ("why did *they* choose it?").
- Questions about the whole paper ("main contribution?"), where top-k retrieval does poorly.
- Questions about a specific spot ("what's in Table 2?", "explain eq. 4").
- Prompt injection hidden in the paper text.
- Very long questions or pasted text; the user asks before indexing has finished.

**System**
- LLM rate limits (429), timeouts, provider outage: retry with backoff, show partial results, offer a resume button.
- The user closes the tab during processing: the job continues and the status can be polled again.
- Concurrent uploads, and orphaned files after failures.

---

## 5. Latency playbook
| Technique | Effect |
|---|---|
| Async ingestion job + progress stepper (SSE/polling) | Upload returns in under 1s; the user sees progress, not a spinner |
| Stream summary **section by section**, generate sections in parallel | First section in about 2–4s instead of waiting 20s+ |
| Token streaming in chat | Time to first token under 1–2s |
| Fast parser (PyMuPDF) by default, heavy parser only when needed | Parsing in under 1s instead of 30s+ |
| Small/fast model for query rewrite and routing | Saves 1–2s per turn |
| Batch embedding calls, local embeddings | Indexing in seconds |
| Prompt caching of the paper prefix | Lower time to first token on later calls |
| Let users chat once indexing is done, even while the summary is still generating | Removes a dependency between the two |
| Skeleton UI, optimistic messages | Feels faster |

## 6. Cost-reduction playbook
- **Hash dedupe**: never re-process the same paper.
- **Generate the summary once and store it**, rather than on every page view.
- **Model tiering**: cheap/fast model for rewriting, routing and suggested questions; a stronger model for the summary and answers.
- **Prompt caching** of the paper text or system prompt for multi-turn chat. Cached input tokens cost much less than normal ones.
- **Local embeddings and reranker**: zero cost per call.
- **Tight context**: rerank down to 5–8 chunks instead of passing 20.
- **Semantic cache** for repeated questions on the same paper.
- **Token budget and max_tokens limits**; record cost per paper in logs.
- Batch APIs for work that doesn't need to be interactive.

---

## 7. UI/UX patterns
- **Split pane**: PDF viewer (react-pdf / pdf.js) on the left; **Summary | Chat** tabs on the right.
- **Clickable citations** `[p.4]` that scroll the viewer and **highlight** the passage. This is the feature that builds the most trust.
- **Processing stepper**: Uploading, then Extracting text, then Indexing, then Summarizing.
- **Summary as section cards** with copy, regenerate-section, and export (Markdown/PDF/BibTeX).
- **Suggested questions** generated from the paper.
- **Select text in the PDF**, then "Explain this / Ask about this".
- Rendered Markdown and **KaTeX math** in answers, plus code blocks and tables.
- "Not found in paper" badge, stop-generating button, retry on error.
- Library sidebar of past papers, dark mode, drag-and-drop, keyboard shortcuts, accessibility (ARIA, focus).
- Friendly empty states and error states ("This looks like a scanned PDF. Try OCR?").

## 8. Extra features ranked by value per effort
1. Clickable citations with highlighting in the PDF (high value).
2. Suggested questions (very cheap).
3. Explain the selected text, with an ELI5/Expert toggle.
4. Extra summary sections: **Limitations**, **Future work**, **Key terms glossary**.
5. Export of the summary and chat (Markdown/PDF), BibTeX.
6. Explaining figures and tables (vision model).
7. Reference list with links (Semantic Scholar / arXiv API).
8. Paper library with history, then compare two papers.
9. Audio summary (TTS), flashcards/quiz.

---

## 9. Suggested tech stack
| Layer | Choice | Why |
|---|---|---|
| Frontend | React + Vite + TypeScript + Tailwind + shadcn/ui | Fast, the stack evaluators expect |
| Data fetching | TanStack Query, fetch-based SSE reader | Caching and retries |
| PDF viewer | `react-pdf` (pdf.js) | Page rendering, text layer for highlighting |
| Markdown/Math | `react-markdown` + `remark-math` + `rehype-katex` | Papers contain equations |
| Backend | **Python FastAPI** + Pydantic | Best PDF and ML ecosystem, async, automatic OpenAPI docs |
| Jobs | FastAPI BackgroundTasks (MVP) → arq/Celery + Redis | Async ingestion |
| DB + vectors | Postgres + pgvector (+ tsvector for BM25) **or** SQLite + Chroma | One store vs zero infrastructure |
| Parsing | PyMuPDF (+ optional GROBID / OCRmyPDF) | Speed and accuracy |
| LLM | Claude / OpenAI / Gemini behind a small provider interface | Swappable |
| Orchestration | Hand-written pipeline (clear) vs LangChain/LlamaIndex (fast but opaque) | Design decision |
| Evaluation | Golden question set + RAGAS-style faithfulness and context recall | Proves quality |
| Observability | Structured logs + Langfuse/OpenTelemetry traces (tokens, latency, cost) | Production readiness |
| Testing | pytest, Vitest, Playwright end-to-end | |
| Delivery | docker-compose, `.env.example`, Makefile, GitHub Actions CI | "Setup instructions to test" |
| Deploy | Vercel (frontend) + Render/Fly/Railway (API) | Live demo link |

## 10. How we prove quality
- **Golden set**: 3–5 diverse papers × 10 questions with expected answers and pages.
- Metrics: retrieval hit@k, answer faithfulness, citation accuracy, latency p50/p95, cost per paper.
- Show the numbers in the README. Few submissions do this, so it stands out.

---

## Sources
- [Elicit vs NotebookLM (2026), Paperguide](https://paperguide.ai/blog/elicit-vs-notebooklm/)
- [SciSpace vs NotebookLM (2026), Paperguide](https://paperguide.ai/blog/scispace-vs-notebooklm/)
- [Elicit vs SciSpace (2026), Paperguide](https://paperguide.ai/blog/elicit-vs-scispace/)
- [Best AI research tools 2026, Toolworthy](https://www.toolworthy.ai/blog/best-ai-research-tools)
- [RAG in production in 2026: beyond naive chunk-and-embed, DEV](https://dev.to/ai_builder/rag-in-production-in-2026-beyond-naive-chunk-and-embed-3803)
- [Production-ready RAG: hybrid search, reranking, memory, Coding Shuttle](https://www.codingshuttle.com/blogs/building-production-ready-rag-hybrid-search-reranking-and-conversational-memory)
- [Contextual RAG with hybrid search and reranking, Analytics Vidhya](https://www.analyticsvidhya.com/blog/2024/12/contextual-rag-systems-with-hybrid-search-and-reranking/)
- [Best open-source PDF-to-Markdown tools 2026](https://themenonlab.blog/blog/best-open-source-pdf-to-markdown-tools-2026)
- [PDF parsing for LLM input](https://nbrosse.github.io/posts/pdf-parsing/pdf-parsing.html)
- [pymupdf4llm vs Docling](https://www.file2markdown.ai/blog/pymupdf4llm-vs-docling)

Note: most of the comparison sources are vendor or practitioner blogs. Use them as directional evidence and benchmark the parsers on our own sample papers.
