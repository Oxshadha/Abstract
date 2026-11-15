import { api } from "@/api/client";

export type VoiceEvent = "listen_started" | "listen_finished" | "dictation_sent" | "dictation_edited";

/** Count one voice event (spec 020 AC9): counts only, never words or audio; failures are ignored. */
export function reportVoice(event: VoiceEvent, engine: string): void {
  void api.POST("/api/v1/usage/voice", { body: { engine, event } }).catch(() => undefined);
}
