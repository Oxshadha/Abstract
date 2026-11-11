# Figures, charts and tables: UX research and proposal

> Research note (2026-11-11), input to specs 007 (chat), 008 (citations and viewer), 009 (enrichment and multimodal) and 015 (reading aids). Proposals here are **not decisions** until approved.

## Why it matters
Research papers put much of their substance in visuals: architecture diagrams, result plots and numeric tables. Benchmarks of question answering on papers show models struggle more with **tables** than with figures, and charts with many data points are still hard for vision models. The UX must make visuals first-class evidence **without adding steps or settings**.

## What existing tools do
| Pattern | Seen in | Lesson |
|---|---|---|
| Ask about a specific chart or table | scienceOS ("chat with figures"), Atlas, Jenni | Users want to point at a visual and ask. NotebookLM and ChatGPT-style chats do not offer direct figure selection, which is an opening |
| Plain-language figure and table explanations | SciSummary | One click, no prompt writing |
| Figure/table cards, hover previews of "Figure 3" mentions | Semantic Reader (Allen AI) | Reading flow stays in place |
| Show the original crop next to extracted data | Recommended by table-extraction reviews | Extraction is imperfect (Docling can silently drop a table that is alone on a page); trust needs a visible source |

## Proposed UX (simple by default)
1. **Figures tab (already in mockups, D27):** a grid of thumbnails with caption and page ("Figure 3 · p. 5"). Tap opens a viewer with zoom and pinch on mobile and four actions only: **Explain**, **Ask about this**, **Go to page**, **Copy**.
2. **Tables render as real tables,** not images: sticky header, horizontal scroll on phones, **Copy as CSV / Markdown**, and a **View original** toggle showing the page crop side by side, so users can check extraction themselves.
3. **Visual evidence appears where it is used:** a summary card ("Key results") shows small thumbnails of the tables or figures that support it; a chat answer whose evidence is a figure shows the thumbnail chip; tapping either highlights the region on the PDF page (extends D23).
4. **"Ask about this region" (snip tool):** drag a rectangle on any PDF page (or long-press on mobile) and ask. This covers anything the parser missed (undetected figures, equations, odd tables) with one universal gesture, sending the crop to the vision model at question time (D12).
5. **Charts: "Extract data" on demand,** producing a table labelled **Approximate values read from the chart**. Never run by default (cost) and never presented as exact.
6. **Progressive and calm:** the Figures tab shows skeleton cards labelled "Finding figures and tables" while background enrichment runs (D68); the summary and chat never wait for it. When enrichment finishes, cards fade in and the summary's provisional badge clears.
7. **Accessibility:** every figure gets a one-line generated alt text; tables are semantic HTML tables (screen-reader friendly); all actions are keyboard reachable.

## Engineering notes
- Enrichment (spec 009) stores per element: type (figure, table, chart), page, bbox, caption, crop in S3 (webp thumbnail + full size), table HTML/JSON, a short description; captions + descriptions are indexed as chunks for retrieval (D12, D51).
- **Missed-table guard:** if the text contains a caption "Table N" but no table element was extracted on that page, show the caption-region crop as a fallback card and offer "Ask about this region".
- Thumbnails are small (about 20 to 40 KB), lazy-loaded; full size loads only in the viewer.
- Vision calls happen only on user action (Explain, Ask, Extract data) or for figures that retrieval selects for an answer; cost per call is logged (D10).
- Chart extraction: current general vision models outperform older chart-specific models such as DePlot on scientific charts, but dense charts remain hard; hence the "approximate" label and on-demand only.

## Open questions for the owner
1. Approve **"Ask about this region"** (snip tool) as a v1 feature (it is new scope; recommended because it covers every visual the parser misses).
2. Approve **chart "Extract data"** as a v1 "Should" (on demand, labelled approximate), or move it to later.

## Sources
- [scienceOS: Shannon update, chat with figures](https://www.scienceos.ai/changelog/shannon-update/)
- [Atlas: chat with a paper comparison](https://www.atlasworkspace.ai/reports/chat-with-a-paper)
- [SciSummary: figure explanations](https://scisummary.com/blog/58-how-scisummary-helps-you-understand-research-papers-faster-and-better)
- [SPIQA: multimodal QA on scientific papers (NeurIPS 2024)](https://proceedings.neurips.cc/paper_files/paper/2024/file/7a19a9d527ed544d1272f07b0f8f934e-Paper-Datasets_and_Benchmarks_Track.pdf)
- [cPAPERS: multimodal conversations in scientific papers](https://arxiv.org/pdf/2406.08398)
- [Self-ensembling VLMs for chart data extraction](https://benchmarklist.com/benchmarks/self_ensembling_vision_language_models_for_chart_data_extraction/)
- [PlotPick: extracting data from scientific figures](https://arxiv.deeppaper.ai/papers/2605.06021v1)
- [Docling technical report](https://arxiv.org/pdf/2501.17887)
- [Docling review: table extraction behaviour](https://thunderbit.com/blog/docling-review)
- [Benchmarking table extraction from scientific documents](https://www.themoonlight.io/review/benchmarking-table-extraction-from-heterogeneous-scientific-extraction-documents)
