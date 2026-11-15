import { describe, expect, it } from "vitest";

import { buildVocabulary, correctTerms } from "./vocabulary";

const ATTENTION = buildVocabulary([
  "Attention Is All You Need",
  "We report BLEU on the WMT 2014 English-to-German task and compare with ConvS2S and GNMT.",
]);
const LORA = buildVocabulary(["LoRA: Low-Rank Adaptation of Large Language Models", "GPT-3 175B"]);

describe("AC7: dictated research terms follow the paper", () => {
  it("builds the vocabulary from acronyms and mixed-case terms only", () => {
    expect(ATTENTION).toEqual(expect.arrayContaining(["BLEU", "WMT", "ConvS2S", "GNMT"]));
    expect(ATTENTION).not.toContain("Attention");
  });

  it("corrects a near miss, a lower-case term and spelled letters, and reports each change", () => {
    const result = correctTerms("what blue score did they get on w m t compared with convs2s", ATTENTION);
    expect(result.text).toBe("what BLEU score did they get on WMT compared with ConvS2S");
    expect(result.changes).toEqual([
      { from: "w m t", to: "WMT" },
      { from: "blue", to: "BLEU" },
      { from: "convs2s", to: "ConvS2S" },
    ]);
  });

  it("restores the paper's casing", () => {
    expect(correctTerms("how does lora reduce parameters for gpt-3", LORA).text).toBe("how does LoRA reduce parameters for GPT-3");
  });

  it("leaves ordinary words alone", () => {
    expect(correctTerms("what is the main result of the paper", ATTENTION)).toEqual({ text: "what is the main result of the paper", changes: [] });
  });
});
