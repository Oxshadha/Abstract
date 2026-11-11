import { Monitor, Moon, Sun } from "lucide-react";
import { useState } from "react";

import { applyTheme, readTheme, type ThemeChoice } from "./theme";

const OPTIONS: { value: ThemeChoice; label: string; Icon: typeof Sun }[] = [
  { value: "system", label: "System", Icon: Monitor },
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
];

/** Segmented control: System, Light, Dark (spec 003 AC3). */
export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(readTheme);
  return (
    <div role="radiogroup" aria-label="Theme" className="inline-flex gap-1 rounded-pill bg-muted p-1">
      {OPTIONS.map(({ value, label, Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={choice === value}
          onClick={() => {
            applyTheme(value);
            setChoice(value);
          }}
          className={`inline-flex min-h-11 items-center gap-1.5 rounded-pill px-3 text-sm ${
            choice === value ? "bg-surface text-text shadow-card" : "text-text-secondary"
          }`}
        >
          <Icon aria-hidden className="size-4" />
          {label}
        </button>
      ))}
    </div>
  );
}
