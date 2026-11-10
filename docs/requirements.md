# Requirements & Traceability

Transcribed from the client brief *"Use Case Document: Research Assistant for PDFs"* (Mitra). The PDF itself is kept out of git (D59).
Every requirement maps to the spec(s) that satisfy it. A requirement is **done** only when its specs are `Implemented`.

## Brief requirements
| ID | Requirement (from brief) | Specs | Notes |
|---|---|---|---|
| R1 | Full-stack app: upload research papers (PDF), auto-generate a structured summary from a predefined template, and offer LLM-powered question answering | all | Objective |
| R2 | Users can upload **a single research paper at a time**, in PDF format | 004 | D57 |
| R3 | **On upload**, generate a summary with sections: **Title & Authors and Abstract**, **Problem Statement**, **Methodology**, **Key Results**, **Conclusion** | 006 | D38: the Quick Summary template matches this exactly |
| R4 | Display the summary in a **readable format** | 006, 008, 003 | Section cards with citations (mockup) |
| R5 | Users can ask **natural-language questions** about the uploaded paper (RAG flows welcome) | 007, 008 | D4 hybrid router |
| R6 | Preferred stack: **React + Python/NodeJS** | 001 | React + FastAPI (D2, D17) |
| R7 | Use of **AI assistance** during development is an advantage (Vercel, Lovable, Cursor AI…) | 017 | AGENTS.md + specs + Claude Code workflow, documented in README (B5); frontend on Vercel |
| R8 | **Extra valuable features** are evaluated on creativity and whether they work | 009–016 | D28, D39 |
| R9 | Deliverable: **complete, functional codebase in Git (preferably GitHub)** with **accessible commit history** | 001 | Conventional Commits (D47) |
| R10 | Submission includes **setup instructions to test the application** | 001, 017 | `cp .env.example .env && make dev` |

## Derived non-functional requirements (from our decisions)
| ID | Requirement | Source | Specs |
|---|---|---|---|
| N1 | Strict per-user/org data isolation | D5, D16, D25 | 002 |
| N2 | Authentication + authorization on every request | D11 | 002 |
| N3 | First summary section visible within seconds; chat answers stream | D12, D40 | 004, 006, 007 |
| N4 | Every answer and summary field is grounded with verifiable citations | D15, D23 | 006, 007, 008 |
| N5 | Features can be added or removed cheaply (modules + flags) | D1, D13 | 001, 011 |
| N6 | Models switchable at runtime; cost tracked per operation | D10 | 005, 011 |
| N7 | WCAG 2.1 AA | D44, palette | 003 + all UI |
| N8 | Measured quality, latency and cost (benchmark + eval) | D21 | 000 |
