# 007 — Chat (RAG) with validated citations

| | |
|---|---|
| **Status** | Implemented except AC18 (2026-11-11): the rerank experiment waits for the Discovery Engine API to be enabled. Approved (owner, 2026-11-11): answers on gemini-3.6-flash (owner re-decided after the price check); hybrid retrieval always (no keyword-first mode); reranker only if an experiment shows a quality gain without significant latency (D80) |
| **Week** | W2 |
| **Decisions** | D9, D15, D16, D22, D23, D49, D50, D52, D53, D69, D74, D78, D79 |
| **Requirements** | R1, R5, N3, N4 |
| **Engineering practices (D67)** | All 7 items of `engineering-practices.md` §3 Spec 007 are included (AC11 to AC17) |
| **Feature flag** | none (core) |
| **Mockups** | `UI/Abstract Research Workspace UI.png` (Ask Abstract panel), opened on demand per D79 |

## Goal
The user asks questions about the open paper and gets a streamed answer, grounded only in that paper, with every claim cited to the passage it came from. They see what Abstract is doing while it works, can stop an answer, keep several conversations per paper, and never get an answer the paper cannot support.

## Scope
**In:** conversations per paper (isolated) · send a message and stream the answer over SSE in the API process (no job queue, D74) · query rewrite and scope check with the cheap model · hybrid retrieval (full-text + vector, RRF) scoped to the paper · answer with the registry's `answer` task and a versioned prompt · citation validation (cited passages must be in the retrieved set; quote located in the passage) · status steps · stop · guardrails · answer and query-embedding caches · Ask Abstract panel UI (history, streaming, citation chips, stop, new conversation).
**Out:** opening a citation in the PDF viewer with the sentence highlighted (008; chips show page and quote until then) · figures and tables in answers (009) · suggested questions and select-to-ask (015) · notes (014).

## Acceptance criteria
**Conversations and sending**
- [x] **AC1** — A paper has any number of conversations; each is isolated (no memory across conversations, D22) and belongs to its owner only (404 for anyone else). A conversation is titled from its first question; it can be renamed and deleted.
- [x] **AC2** — `POST /conversations/{id}/messages` stores the user message and streams the answer as SSE in the same response: `status` events (steps), `delta` events (text batches), `citations`, and a final `done` with the saved message id. Chat never uses the job queue (D74).
- [x] **AC3** — Follow-ups use the last 8 turns plus a rolling summary of older turns (D22); the cheap `rewrite` task turns the question into a standalone search query and classifies it (paper question, greeting, off-topic, unsafe) in one call.

**Retrieval and answering**
- [x] **AC4** — Retrieval is hybrid and scoped to the paper (D49, D50): full-text (`websearch_to_tsquery`) and vector (cosine, exact scan by `paper_id`, embedding the query with the paper's recorded embedding model) merged with RRF; the top passages (about 8) go to the `answer` task with their page ranges, as delimited data (rule 8). Chat opens when hybrid search is ready (owner, D80). Only if embedding the question fails at answer time (provider outage) does retrieval fall back to keywords, and that answer is labelled "Answered from a keyword search" (degraded mode, never the normal path).
- [x] **AC5** — The answer prompt (`answer@1`, versioned) requires every factual sentence to cite its passage (`[S3]`). After streaming, citations are validated: markers for passages outside the retrieved set are removed; each cited sentence is matched to its supporting sentence in the passage (rapidfuzz) to store a quote and page for 008; an answer with no valid citation is replaced by a calm "I could not find this in the paper" with suggestions (rule 9).
- [x] **AC6** — Guardrails (D74): answers only from the paper; off-topic or general questions get a polite scoped refusal with suggested questions; user text is length-limited and screened for injection patterns; the system prompt and other users' data are never revealed; refusals and blocks are logged without content. An injection and off-topic test set (OWASP LLM01 style) runs in CI with the fake provider.
- [x] **AC7** — Visible progress (D74): `status` events "Understanding your question", "Searching the paper", "Reading p. 4 to 7", "Writing the answer", shown like an activity line; they describe pipeline steps, never model reasoning.
- [x] **AC8** — Caching (D74): an answer cache per user and paper, keyed by the normalized question, paper version, model and prompt version (never shared across users, D16), returns repeated questions instantly at no cost and is cleared when the paper is re-indexed; query embeddings are cached.

**Workspace UI**
- [x] **AC9** — The Ask Abstract panel (opened on demand, D79) shows the conversation with user and assistant turns as in the mockup, an input with send (Enter) and newline (Shift+Enter), the activity line while working, citation chips (`p. 2 (Sec. 2.1)`) that expand to the quoted passage, a conversation switcher with "New conversation", and an empty state with example questions.
- [x] **AC10** — Answers render with the safe Markdown renderer from 006 (AC14); failures show a calm message with Retry; when chat is not available yet (text not indexed) the input explains why and enables itself when ready.

**Practices (§3 Spec 007)**
- [x] **AC11** — Sending carries an `Idempotency-Key`; a retried send does not create a second turn or a second LLM call (it replays the stored answer).
- [x] **AC12** — The answer stream sends a `:` heartbeat every 15 s; the stream route is marked not to be buffered by proxies.
- [x] **AC13** — When the client disconnects or presses Stop, the server cancels the provider request within 2 s, saves the partial answer marked `stopped`, and records usage for the tokens actually generated.
- [x] **AC14** — The client aborts the in-flight stream when the paper or conversation changes and ignores events whose `conversation_id` does not match.
- [x] **AC15** — Tokens are appended in batches per animation frame; the ARIA live region announces completed sentences, not every token.
- [x] **AC16** — Messages are capped at 4,000 characters on the server and the client.
- [x] **AC17** — Conversation history uses cursor pagination with `limit` <= 50.

**Reranking by measurement (owner, D80)**
- [ ] **AC18** — A `Reranker` port with a Vertex ranking adapter (Google, no new provider) sits between retrieval and the answer, off by default (registry task `rerank` disabled). Experiment R in the eval harness compares answers on the golden questions with and without reranking (citation hit rate, answer accuracy, added latency p50/p95); the report goes to the owner and the reranker is enabled only if quality improves clearly without significant latency.

## API contract
| Method | Path | Auth | Response | Errors |
|---|---|---|---|---|
| GET | `/papers/{id}/conversations` | user, `chat.read` | `200 {items}` | 404 |
| POST | `/papers/{id}/conversations` | user, `chat.create` | `201 {conversation}` | 404, 409 chat not available |
| PATCH | `/conversations/{id}` | user, `chat.update` | `200 {conversation}` | 404, 422 |
| DELETE | `/conversations/{id}` | user, `chat.delete` | `204` | 404 |
| GET | `/conversations/{id}/messages` | user, `chat.read` | `200 {items, next_cursor}` | 404 |
| POST | `/conversations/{id}/messages` | user, `chat.create`, `Idempotency-Key` | SSE `status`, `delta`, `citations`, `done`, `error` | 404, 409, 413, 422, 429 |

## Data model (migration 0006)
`conversations` (org_id, paper_id, owner_id, title, rolling_summary, created_at, updated_at) · `messages` (org_id, conversation_id, role `user`/`assistant`, content, status `complete`/`stopped`/`failed`/`refused`, retrieval_mode `hybrid`/`keyword`, model, prompt_version, created_at; cursor index) · `message_citations` (org_id, message_id, marker, chunk_id, page_start, page_end, quote, score). All org-scoped with forced RLS (002 conformance test). Answer cache in Redis with a TTL.

## Edge cases & failure modes
Question before text is ready (409, input disabled) · all providers down (calm error, user message kept, Retry) · stop mid-stream (partial saved) · very long question (413 / client cap) · injection inside the paper text (data only; never followed) · paper deleted during a stream (stream ends) · two tabs sending in the same conversation (both saved in order).

## Latency / cost budget
First status event < 300 ms; first answer token p95 < 2.5 s on a warm cache of the paper; about $0.0065 per question (cost model); cached answers $0 and instant.

## Test plan
Unit: rewrite/classify parsing, RRF, citation parsing and validation, guardrail screens, cache keys. Integration: send and stream end to end with the fake provider (steps, deltas, citations, done), idempotent replay, stop and partial save, keyword-only mode, RLS on the new tables, pagination. Injection and off-topic test set in CI. Frontend: panel states (empty, streaming, stopped, failed, refused), batching and live region, abort on switch, axe. Playwright: ask a question on the happy path.

## Implementation notes (2026-11-11)
- **Verified with real Gemini 3.6 Flash** on `make dev`: the Playwright happy path asks a question in the workspace and gets a cited answer at desktop and phone sizes.
- **Found live:** Gemini groups citation markers (`[S1, S2]`); the validator now expands grouped forms, with a test using the exact model output.
- **Memory (owner question):** short-term memory is the last 8 turns plus a rolling summary, and follow-ups are rewritten into standalone questions (D22). No memory across conversations; long-term memory the user controls comes with notes (014) and preferences (015).
- **AC18 open:** the reranker port, Vertex adapter and chat wiring are built and off by default; experiment R needs the Discovery Engine API enabled on the GCP project (owner action), then runs with the 006 AC6 experiment.
- **Tests no longer share the dev stack's Redis** (an unreachable default in test settings).

## Open questions (owner)
- **Q1 (answered):** `gemini-3.6-flash` for answers (owner re-decided after current prices showed gemini-3.5-flash at about twice the cost); `gemini-3.5-flash-lite` for rewrite and routing.
- **Q2 (answered):** reranker decided by measurement (AC18).
- **Q3 (answered):** hybrid search always; no keyword-first mode now (D78 waits for the production benchmark); keywords only as a labelled fallback when embedding fails.
