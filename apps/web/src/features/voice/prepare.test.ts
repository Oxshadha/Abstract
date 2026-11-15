import { describe, expect, it } from "vitest";

import { prepareForSpeech, speakMath, splitSentences } from "./prepare";

// Real answer shapes from the dev library (Attention Is All You Need, LoRA, BERT).
describe("AC5c: text is prepared to sound like a person", () => {
  it("drops citation markers in every form", () => {
    expect(prepareForSpeech("The Transformer uses attention alone [1]. It trains faster [S2], [3, 4, 5] and [S1; S3].")).toBe(
      "The Transformer uses attention alone. It trains faster, and.",
    );
    expect(prepareForSpeech("Results are on p. 8 (p. 8) and pages [pp. 2-5].")).toBe("Results are on p. 8 and pages.");
  });

  it("drops Markdown symbols, headings and bullets but keeps the words", () => {
    expect(prepareForSpeech("## Method\n- **Multi-head** attention\n- *Scaled* dot products")).toBe(
      "Method. Multi-head attention. Scaled dot products",
    );
  });

  it("drops status labels", () => {
    expect(prepareForSpeech("Verified: BLEU of 28.4 on WMT 2014.")).toBe("BLEU of 28.4 on WMT 2014.");
  });

  it("reads short maths in words and long maths as formula", () => {
    expect(speakMath("d_k = d_v").trim()).toBe("d k equals d v");
    expect(prepareForSpeech("They set $d_k = d_v = 64$.")).toBe("They set d k equals d v equals 64.");
    expect(prepareForSpeech("Attention is $\\mathrm{softmax}(QK^T / \\sqrt{d_k}) V$ for all heads in parallel.")).toContain("formula");
  });

  it("skips code, links and tables", () => {
    const text = prepareForSpeech("Run `pip install x` or see https://arxiv.org/abs/1706.03762.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nSee [the code](https://github.com/x).");
    expect(text).not.toMatch(/pip|arxiv|github|\|/);
    expect(text).toContain("See the code");
  });
});

describe("AC5: spoken sentence by sentence", () => {
  it("splits sentences without breaking on abbreviations or decimals", () => {
    expect(splitSentences("Vaswani et al. propose a model. It reaches 28.4 BLEU, e.g. on WMT. Done!")).toEqual([
      "Vaswani et al. propose a model.",
      "It reaches 28.4 BLEU, e.g. on WMT.",
      "Done!",
    ]);
  });

  it("keeps a last sentence without a full stop and drops empty pieces", () => {
    expect(splitSentences("One. . Two")).toEqual(["One.", "Two"]);
  });
});
