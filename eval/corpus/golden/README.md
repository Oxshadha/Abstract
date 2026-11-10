# Verifying golden data (about 10 minutes per paper)

The benchmark only scores items you have verified. Each `<paper>.yaml` was drafted by an LLM
and must be checked against the PDF in `eval/corpus/pdfs/<paper>.pdf`.

## Steps per file
1. Open the PDF next to the YAML.
2. **present_fields**: does the paper clearly contain each section (abstract, problem
   statement, methodology, key results, conclusion)? Fix any `true`/`false` that is wrong, then
   add a line `present_fields_verified: true` at the top level.
3. **facts** (5): go to the page, check the number(s) appear exactly as written.
   Correct the text or page if needed, then set `verified: true`. Delete a fact that is wrong
   and cannot be fixed (better 4 good facts than 5 doubtful ones).
4. **questions** (8): check the answer and page(s) against the PDF. For the two
   `unanswerable` questions, make sure the paper really does not answer them.
   Set `verified: true` on each one you accept.
5. **layout_probes** (two-column papers only): find `first` at the bottom of the left column
   and `second` at the top of the right column on that page. If they are really consecutive
   in reading order, set `verified: true`; otherwise delete the probe.

## Rules
- Only edit values; keep the field names.
- When unsure, leave `verified: false`. Unverified items are ignored, not counted as wrong.
- Commit with `test(eval): verify golden data for <paper>`.

## Quick check
```
make eval EXP=B IDS="<paper>" RUNS=1
```
runs one experiment on one paper and shows whether your verified items score as expected.
