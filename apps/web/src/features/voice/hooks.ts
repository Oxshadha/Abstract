import { useEffect, useState } from "react";

import { useFlag } from "@/features/flags/api";

import { engines, type Voice } from "./engines";
import { reader } from "./reader";
import { reportVoice } from "./usage";

export function useVoices(): Voice[] {
  const [voices, setVoices] = useState<Voice[]>(() => engines.output.voices());
  useEffect(() => engines.output.onVoicesChanged(() => { setVoices(engines.output.voices()); }), []);
  return voices;
}

/** Spec 020 AC11: Listen shows only where it works: flag on, an engine and at least one voice. */
export function useCanListen(): boolean {
  const on = useFlag("voice_listen");
  const voices = useVoices();
  return on && engines.output.supported() && voices.length > 0;
}

/** AC11: Speak shows only where it works (flag on and the browser can recognize speech). */
export function useCanSpeak(): boolean {
  return useFlag("voice_speak") && engines.input.supported();
}

/** AC5: leaving the paper stops reading. */
export function useStopReadingOnLeave(paperId: string): void {
  useEffect(() => () => { reader.stop(); }, [paperId]);
}

/** AC9: once a dictated question is sent, count whether it was sent as dictated or edited. */
export function countDictation(dictated: string | null, sent: string): void {
  if (dictated === null) return;
  reportVoice(dictated.trim() === sent.trim() ? "dictation_sent" : "dictation_edited", engines.input.engine);
}
