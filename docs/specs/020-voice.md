# 020 — Voice: listen to the summary, ask by speaking

| | |
|---|---|
| **Status** | Approved (owner, 2026-11-15): browser-engine baseline with the upgrade path; a speaker icon on chat answers is in scope (D102) |
| **Week** | after 017 and 019 |
| **Decisions** | D88 (reading aids), D101 (chat), D102 |
| **Engineering practices (D67)** | No new §3 items; accessibility (WCAG 2.1 AA) applies |
| **Feature flag** | `voice_listen`, `voice_speak` (on by default where the browser supports them) |
| **Mockup** | none; controls follow `docs/design-principles.md` (icons with names, no native controls) |

## Goal
A reader can **listen** to a paper's summary instead of reading it, and **ask** Ask Abstract a question by speaking. The first version costs nothing to run: it uses the speech engines built into the browser, behind small interfaces so a better engine can replace them later without changing the feature.

## Scope
**In:**
- **Listen:** a Listen control on the Summary panel that reads the summary aloud, field by field, with the sentence being read highlighted; and a small speaker icon on each Ask Abstract answer.
- **Speak:** a microphone button in the Ask Abstract composer that turns speech into text in the box; the reader reviews it and presses Send.
- Two frontend interfaces, `SpeechOutput` and `SpeechInput`, with browser adapters (Web Speech API) as the baseline.
- Paper-aware correction of dictated research terms, in the browser.

**Out (later, each a new adapter behind the same interface, owner decision when needed):**
- Natural AI voices for listening (Kokoro or Piper in the browser, a 40 to 80 MB first download).
- Better recognition for speaking (Gemini transcription through the LLM gateway, about $0.001 a question, or Whisper in the browser).
- Reading notes aloud.
- Voice conversations (speaking answers back automatically).

## Why the browser engines first
| | Browser (baseline) | In-browser model (Kokoro, Piper, Whisper) | Cloud API (Gemini, Whisper API, TTS APIs) |
|---|---|---|---|
| Running cost | $0 | $0 | per use |
| Download | none | 40 to 150 MB | none |
| Quality | good, varies by device; jargon weaker for speaking | natural, consistent | best |
| Privacy | listen: on device by default; speak: the browser's service (Google in Chrome, Apple in Safari) | on device | our provider |
| Support | Chrome, Edge, Safari (speaking not in Firefox) | all modern browsers, slow on phones | all |

The baseline validates the feature at no cost; usage numbers (AC9) decide when an upgrade is worth it.

## Acceptance criteria

### Listen
- [ ] **AC1** — **Listen to the summary.** The Summary panel has a Listen control. It reads the title and authors, then each field in order: the field name ("Methodology."), then its text. Citation markers, status labels (Verified, Inferred) and Markdown symbols are not read. Fields that are *Not reported* are read as "not reported".
- [ ] **AC2** — **Follow along.** The sentence being read is highlighted and kept in view; the field being read is marked. Highlighting is off with reduced motion turned on (the text stays readable).
- [ ] **AC3** — **Controls.** Play, pause and resume, stop, skip to the next or previous field, and speed from 0.75× to 2×. Keyboard reachable with visible names; the chosen speed and voice are remembered on the device.
- [ ] **AC4** — **Private by default.** Only voices that run on the device are offered (`localService`), so the summary text does not leave the device; online voices appear only after the reader turns on "Show online voices", with a one-line note that the text is sent to the browser's speech service.
- [ ] **AC5b** — **Listen to an answer.** Each Ask Abstract answer has a small speaker icon (named "Listen to this answer") that reads that answer with the same controls and voice settings; starting one stops any other reading.
- [ ] **AC5c** — **Sounds like a person, not a machine.** Before anything is spoken, the text is prepared: citation markers ([1], [S1], [1, 4, 5]), source chips, status labels and Markdown symbols are removed; maths is read in words where short (for example "d k equals d v") and as "formula" where long; code, URLs and table markup are skipped; abbreviations with dots (e.g., et al.) do not end a sentence. Unit tests cover each rule on real answers from the dev library.
- [ ] **AC5** — **Reliable on long summaries.** Text is spoken sentence by sentence, so long summaries do not stop part way (a Chrome limit), pause and resume work, and leaving the paper stops speech.

### Speak
- [ ] **AC6** — **Ask by speaking.** The Ask Abstract composer has a microphone button. While listening it shows that it is listening and the words appear in the box as they are recognized; stopping, or a pause of about 2 seconds, ends it. **Nothing is sent automatically**: the reader reviews the text and presses Send.
- [ ] **AC7** — **Research terms.** After dictation, words that closely match the paper's own vocabulary (its title, section headings and acronyms such as BLEU, WMT, LoRA) are corrected in the box ("blue score" → "BLEU score"), with the change visible and undoable. Runs in the browser, no model call.
- [ ] **AC8** — **Permission and privacy.** The browser's microphone permission is asked only when the button is first pressed; a refusal shows how to allow it. The first use shows a one-line note on where speech is processed (Google in Chrome, Apple in Safari).

### Shared
- [ ] **AC9** — **Know when to upgrade.** The app counts, per engine, how often dictated text is edited before sending and how often Listen is started and finished. Counts only, never words or audio (D76), visible in the Admin overview.
- [ ] **AC10** — **Swappable engines.** Listen and Speak use `SpeechOutput` and `SpeechInput` interfaces; the browser adapters are one implementation each, chosen in one place, so a later engine is a new adapter with no change to the panels.
- [ ] **AC11** — **Only where it works.** Each control is hidden when its flag is off or the browser has no support (Speak in Firefox); nothing breaks or shows an error.
- [ ] **AC12** — **Quality bar.** Works on phones (tap to start; screen lock stopping speech on iPhone is a browser limit and is stated in the help text), in light and dark, in Chromium, WebKit and Firefox where supported; axe passes; no em or en dashes in new UI text; the controls follow the design principles.

## API contract
No new endpoints for the baseline. AC9 counts use the existing usage events (one small `POST /api/v1/usage/voice` with counts only, rate-limited, if no suitable event exists; decided in the build).

## Data model changes
None for the baseline (AC9 reuses usage counters, or one counts table if needed; no text or audio is ever stored).

## Edge cases & failure modes
- No voices installed (some Linux browsers): Listen is hidden.
- Recognition errors or network loss (Chrome's service): the box keeps what was recognized; a short message says to try again or type.
- Very long summaries: sentence queue with pause and resume; stopping clears the queue.
- Switching paper or tab: speech stops; recognition stops.
- Mixed languages: the voice follows the browser language; papers in other languages are read with the closest available voice.

## Latency / cost budget
$0 running cost. Listen starts within 300 ms of pressing play; dictated words appear while speaking.

## Test plan
- Unit (Vitest): text preparation (markers, labels, Markdown stripped), sentence splitting, vocabulary correction, adapters with a fake speech engine.
- Component: controls, remembered settings, highlighting, hidden when unsupported, nothing sent without Send.
- Browser checks (Playwright, by hand for audio): Chromium, WebKit, Firefox on desktop and phone sizes.

## Owner answers (2026-11-15)
- **Q1:** approved: the browser-engine baseline, with better engines later as new adapters.
- **Q2:** yes: a small speaker icon on chat answers, read without citation markers or other machine-like text (AC5b, AC5c).
