import { Globe, Headphones, Pause, Play, SkipBack, SkipForward, Square, Volume2 } from "lucide-react";
import { Select } from "@/components/menu/Select";

import { useVoices } from "./hooks";
import { RATES, reader, useReader, useVoiceSettings, type Segment } from "./reader";

const icon = "inline-flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-muted disabled:opacity-40";

function VoiceSettings() {
  const settings = useVoiceSettings();
  const voices = useVoices();
  // AC4: voices on the device only, unless the reader chooses online ones.
  const offered = voices.filter((v) => v.local || settings.showOnline);
  const lang = typeof navigator === "undefined" ? "en" : navigator.language.slice(0, 2);
  const sorted = [...offered].sort((a, b) => Number(b.lang.startsWith(lang)) - Number(a.lang.startsWith(lang)) || a.name.localeCompare(b.name));
  const current = sorted.find((v) => v.id === settings.voiceId) ? (settings.voiceId ?? "") : "";
  return (
    <>
      <Select
        label="Speed"
        compact
        value={String(settings.rate)}
        options={RATES.map((r) => ({ value: String(r), label: `${String(r)}×` }))}
        onChange={(value) => { reader.updateSettings({ rate: Number(value) }); }}
        width="w-28"
      />
      <Select
        label="Voice"
        compact
        value={current}
        placeholder="Default voice"
        options={[{ value: "", label: "Default voice" }, ...sorted.map((v) => ({ value: v.id, label: v.name, description: `${v.lang}${v.local ? "" : ", online"}` }))]}
        onChange={(value) => { reader.updateSettings(value ? { voiceId: value } : { voiceId: undefined }); }}
        width="w-64"
        footer={<p className="px-2 py-1.5 text-xs text-text-secondary">On iPhone, locking the screen stops reading.</p>}
      />
      <button
        type="button"
        aria-pressed={settings.showOnline}
        aria-label="Show online voices"
        title="Show online voices"
        onClick={() => { reader.updateSettings({ showOnline: !settings.showOnline }); }}
        className={`${icon} ${settings.showOnline ? "bg-muted" : ""}`}
      >
        <Globe aria-hidden className="size-4" />
      </button>
    </>
  );
}

interface Props {
  owner: string; // "summary:<id>" or "answer:<id>"
  segments: () => Segment[];
  variant: "summary" | "answer";
}

/** Listen (spec 020 AC1, AC3, AC5b): a button, and while reading, the controls. */
export function ListenControls({ owner, segments, variant }: Props) {
  const state = useReader();
  const settings = useVoiceSettings();
  const mine = state.owner === owner;
  const playing = mine && state.status === "playing";

  if (!mine) {
    return variant === "summary" ? (
      <button
        type="button"
        onClick={() => { reader.start(owner, segments()); }}
        className="inline-flex min-h-11 items-center gap-2 rounded-md border border-border px-3 hover:bg-muted"
      >
        <Headphones aria-hidden className="size-4" />
        Listen
      </button>
    ) : (
      <button type="button" aria-label="Listen to this answer" title="Listen to this answer" onClick={() => { reader.start(owner, segments()); }} className={icon}>
        <Volume2 aria-hidden className="size-4" />
      </button>
    );
  }

  return (
    <div className="flex w-full flex-col gap-1">
      <div role="toolbar" aria-label="Reading controls" className="flex flex-wrap items-center gap-1 rounded-lg border border-border bg-surface p-1">
        {variant === "summary" && (
          <button type="button" aria-label="Previous section" onClick={() => { reader.previous(); }} className={icon}>
            <SkipBack aria-hidden className="size-4" />
          </button>
        )}
        <button
          type="button"
          aria-label={playing ? "Pause" : "Resume"}
          onClick={() => { if (playing) reader.pause(); else reader.resume(); }}
          className={icon}
        >
          {playing ? <Pause aria-hidden className="size-4" /> : <Play aria-hidden className="size-4" />}
        </button>
        {variant === "summary" && (
          <button
            type="button"
            aria-label="Next section"
            disabled={state.segment + 1 >= state.segments.length}
            onClick={() => { reader.next(); }}
            className={icon}
          >
            <SkipForward aria-hidden className="size-4" />
          </button>
        )}
        <button type="button" aria-label="Stop reading" onClick={() => { reader.stop(owner); }} className={icon}>
          <Square aria-hidden className="size-4" />
        </button>
        <span className="ml-auto flex flex-wrap items-center gap-1">
          <VoiceSettings />
        </span>
      </div>
      {settings.showOnline && (
        <p className="px-1 text-xs text-text-secondary">Online voices send the text to your browser&apos;s speech service.</p>
      )}
    </div>
  );
}
