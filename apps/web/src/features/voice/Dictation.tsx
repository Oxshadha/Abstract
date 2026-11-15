import { useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Mic, Square, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { engines } from "./engines";
import { buildVocabulary, correctTerms, type Correction } from "./vocabulary";

const SILENCE_MS = 2000; // AC6: a pause of about 2 seconds ends listening
const BARS = 32;
const NOTED_KEY = "abstract.voice.noted";

/** The paper's own terms (AC7): its title, cached summary text and this chat. */
function useVocabulary(paperId: string): () => string[] {
  const client = useQueryClient();
  return () => {
    const texts: string[] = [];
    for (const [, data] of client.getQueriesData({ queryKey: ["papers", paperId] })) texts.push(JSON.stringify(data ?? ""));
    for (const [, data] of client.getQueriesData({ queryKey: ["summaries"] })) texts.push(JSON.stringify(data ?? ""));
    for (const [, data] of client.getQueriesData({ queryKey: ["chat"] })) texts.push(JSON.stringify(data ?? ""));
    return buildVocabulary(texts);
  };
}

/** Live microphone levels for the waveform, or null where the browser will not share them. */
function useLevels(active: boolean): number[] | null {
  const [levels, setLevels] = useState<number[] | null>(null);
  useEffect(() => {
    if (!active || typeof navigator === "undefined" || !("mediaDevices" in navigator) || typeof AudioContext !== "function") return;
    let stopped = false;
    let frame = 0;
    let stream: MediaStream | null = null;
    let context: AudioContext | null = null;
    const history: number[] = Array.from({ length: BARS }, () => 0);
    void navigator.mediaDevices.getUserMedia({ audio: true }).then((s) => {
      if (stopped) {
        s.getTracks().forEach((t) => { t.stop(); });
        return;
      }
      stream = s;
      context = new AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 512;
      context.createMediaStreamSource(s).connect(analyser);
      const data = new Uint8Array(analyser.fftSize);
      let last = 0;
      const tick = (now: number) => {
        if (stopped) return;
        if (now - last > 70) {
          last = now;
          analyser.getByteTimeDomainData(data);
          let sum = 0;
          for (const v of data) sum += ((v - 128) / 128) ** 2;
          history.shift();
          history.push(Math.min(1, Math.sqrt(sum / data.length) * 4));
          setLevels([...history]);
        }
        frame = requestAnimationFrame(tick);
      };
      frame = requestAnimationFrame(tick);
    }).catch(() => { setLevels(null); });
    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      stream?.getTracks().forEach((t) => { t.stop(); });
      void context?.close();
      setLevels(null);
    };
  }, [active]);
  return levels;
}

function Waveform({ levels }: { levels: number[] | null }) {
  const bars = levels ?? Array.from({ length: BARS }, () => 0);
  return (
    <span aria-hidden className="flex h-8 w-0 min-w-0 flex-1 items-center justify-end gap-[3px] overflow-hidden">
      {bars.map((level, i) => (
        <span
          key={i}
          className={`w-1 shrink-0 rounded-full bg-text ${levels ? "" : "motion-safe:animate-pulse"}`}
          style={{ height: `${String(4 + Math.round(level * 24))}px`, opacity: level > 0.05 ? 0.9 : 0.35 }}
        />
      ))}
    </span>
  );
}

interface Props {
  paperId: string;
  disabled: boolean;
  /** Dictated text goes into the box for review. */
  onReview: (text: string) => void;
  /** The reader pressed send while listening. */
  onSend: (text: string) => void;
  /** Tells the composer what was dictated, to count sent-as-is or edited (AC9). */
  onDictated: (text: string) => void;
  /** Listening starts: the composer remembers what was already typed. */
  onStart: () => void;
  children: (mic: React.ReactNode) => React.ReactNode;
}

type Ending = "review" | "send" | "cancel";

/**
 * Ask by speaking (spec 020 AC6 to AC8, D104), shaped like a familiar voice composer: the
 * microphone sits in the box; while listening the box becomes a bar with cancel, a live waveform,
 * stop (the words go into the box to review) and send (stop and send now). Nothing is ever sent
 * without the reader pressing send.
 */
export function Dictation({ paperId, disabled, onReview, onSend, onDictated, onStart, children }: Props) {
  const [listening, setListening] = useState(false);
  const [heard, setHeard] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [changes, setChanges] = useState<{ corrected: string; original: string; list: Correction[] } | null>(null);
  const [noted] = useState(() => {
    try { return localStorage.getItem(NOTED_KEY) === "1"; } catch { return false; }
  });
  const stopRef = useRef<(() => void) | null>(null);
  const ending = useRef<Ending>("review");
  const heardRef = useRef("");
  const silence = useRef<ReturnType<typeof setTimeout> | null>(null);
  const vocabulary = useVocabulary(paperId);
  const levels = useLevels(listening);

  useEffect(() => () => { stopRef.current?.(); }, []);

  const finish = () => {
    if (silence.current) clearTimeout(silence.current);
    setListening(false);
    stopRef.current = null;
    const raw = heardRef.current.trim();
    const how = ending.current;
    heardRef.current = "";
    setHeard("");
    if (!raw || how === "cancel") return;
    const result = correctTerms(raw, vocabulary());
    setChanges(how === "review" && result.changes.length ? { corrected: result.text, original: raw, list: result.changes } : null);
    onDictated(result.text);
    if (how === "send") onSend(result.text);
    else onReview(result.text);
  };

  const start = () => {
    onStart();
    setError(null);
    setChanges(null);
    ending.current = "review";
    heardRef.current = "";
    setListening(true);
    if (!noted) {
      try { localStorage.setItem(NOTED_KEY, "1"); } catch { /* the note shows again next visit */ }
    }
    const lang = typeof navigator === "undefined" ? "en-US" : navigator.language;
    stopRef.current = engines.input.listen(lang, {
      onText: (text) => {
        heardRef.current = text;
        setHeard(text);
        if (silence.current) clearTimeout(silence.current);
        silence.current = setTimeout(() => { stopRef.current?.(); }, SILENCE_MS);
      },
      onEnd: finish,
      onError: (reason) => {
        if (reason === "no-speech") return;
        setError(
          reason === "not-allowed"
            ? "The microphone is blocked. Allow it for this site in your browser's settings, then try again."
            : "Speech could not be recognized right now. Try again, or type your question.",
        );
      },
    });
  };

  const end = (how: Ending) => {
    ending.current = how;
    if (stopRef.current) stopRef.current();
    else finish();
  };

  const mic = (
    <button
      type="button"
      aria-label="Ask by speaking"
      title="Ask by speaking"
      disabled={disabled}
      onClick={start}
      className="inline-flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-muted disabled:opacity-50"
    >
      <Mic aria-hidden className="size-5" />
    </button>
  );

  return (
    <>
      {listening ? (
        <div className="flex min-w-0 basis-full flex-col gap-1.5">
          <p aria-live="polite" className="min-h-6 px-2 font-reading text-text-secondary">{heard || "Listening"}</p>
          <div role="group" aria-label="Speaking" className="flex min-w-0 items-center gap-2">
            <button type="button" aria-label="Cancel" onClick={() => { end("cancel"); }} className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-muted hover:opacity-80">
              <X aria-hidden className="size-5" />
            </button>
            <Waveform levels={levels} />
            <button type="button" aria-label="Stop and review" onClick={() => { end("review"); }} className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-muted hover:opacity-80">
              <Square aria-hidden className="size-3.5 fill-current" />
            </button>
            <button type="button" aria-label="Send" onClick={() => { end("send"); }} className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-primary text-primary-text hover:opacity-90">
              <ArrowUp aria-hidden className="size-5" />
            </button>
          </div>
          {!noted && <p className="px-2 text-xs text-text-secondary">{`Your speech is turned into text by ${engines.input.processedBy}.`}</p>}
        </div>
      ) : (
        children(mic)
      )}
      {error && <p role="alert" className="basis-full px-2 text-sm">{error}</p>}
      {changes && !listening && (
        <p className="flex basis-full flex-wrap items-center gap-x-2 px-2 text-sm text-text-secondary">
          <span>{`Matched the paper's terms: ${changes.list.map((c) => `${c.from} to ${c.to}`).join(", ")}.`}</span>
          <button
            type="button"
            onClick={() => {
              onReview(changes.original);
              onDictated(changes.original);
              setChanges(null);
            }}
            className="min-h-9 underline"
          >
            Undo
          </button>
        </p>
      )}
    </>
  );
}
