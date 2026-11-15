import { AudioLines, Globe, Headphones, Pause, Play, SkipBack, SkipForward, Square, Volume2 } from "lucide-react";
import { Menu } from "@/components/menu/Menu";
import { Select } from "@/components/menu/Select";

import { useVoices } from "./hooks";
import { RATES, reader, useReader, useVoiceSettings, type Segment } from "./reader";

const icon = "inline-flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-muted disabled:opacity-40";

/** Speed and voice (AC3, AC4): a compact speed picker and one menu for the voice. */
function VoiceSettings() {
  const settings = useVoiceSettings();
  const voices = useVoices();
  // AC4: voices on the device only, unless the reader chooses online ones.
  const offered = voices.filter((v) => v.local || settings.showOnline);
  const lang = typeof navigator === "undefined" ? "en" : navigator.language.slice(0, 2);
  const sorted = [...offered].sort((a, b) => Number(b.lang.startsWith(lang)) - Number(a.lang.startsWith(lang)) || a.name.localeCompare(b.name));
  const current = sorted.find((v) => v.id === settings.voiceId)?.id;
  return (
    <>
      <Select
        label="Speed"
        compact
        value={String(settings.rate)}
        options={RATES.map((r) => ({ value: String(r), label: `${String(r)}×` }))}
        onChange={(value) => { reader.updateSettings({ rate: Number(value) }); }}
        width="w-24"
        align="right"
      />
      <Menu
        label="Voice"
        trigger={<AudioLines aria-hidden className="size-4" />}
        items={[
          { label: "Default voice", checked: current === undefined, onSelect: () => { reader.updateSettings({ voiceId: undefined }); } },
          ...sorted.map((v) => ({ label: v.local ? v.name : `${v.name} (online)`, checked: v.id === current, onSelect: () => { reader.updateSettings({ voiceId: v.id }); } })),
          { label: "Show online voices", icon: <Globe aria-hidden className="size-4" />, checked: settings.showOnline, onSelect: () => { reader.updateSettings({ showOnline: !settings.showOnline }); } },
        ]}
        footer={
          <p className="max-w-64 px-2 py-1.5 text-xs text-text-secondary">
            {settings.showOnline ? "Online voices send the text to your browser's speech service. " : ""}
            On iPhone, locking the screen stops reading.
          </p>
        }
      />
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
      <div role="toolbar" aria-label="Reading controls" className="flex items-center gap-0.5 rounded-lg border border-border bg-surface p-1">
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
        <span className="ml-auto flex items-center gap-0.5">
          <VoiceSettings />
        </span>
      </div>
    </div>
  );
}
