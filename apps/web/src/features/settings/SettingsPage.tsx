import { useMutation, useQuery } from "@tanstack/react-query";
import { BarChart3, FileText, LogOut, MessageSquare, Palette, Sparkles, Trash2, User, type LucideIcon } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { fetchMe } from "@/api/me";
import { useAuthState } from "@/auth/state";
import { Dialog, buttonSecondary, inputClass } from "@/components/dialog/Dialog";
import { ListRowSkeleton, Loading } from "@/components/feedback/Skeleton";
import { FieldError } from "@/components/status/FieldError";
import { DESTRUCTIVE } from "@/components/status/tone";
import { toast } from "@/components/status/toast";
import { ThemeToggle } from "@/theme/ThemeToggle";

import { deleteAccount, getUsage, settingsKeys, type Meter } from "./api";
import { METER_LABELS, meterValue, resetLabel } from "./format";

const METER_ICONS: Record<Meter["key"], LucideIcon> = { papers: FileText, messages: MessageSquare, ai: Sparkles };

function initials(name: string | null | undefined): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  return (parts.slice(0, 2).map((p) => p[0]).join("") || "?").toUpperCase();
}

function Section({ title, icon: Icon, children }: { title: string; icon: LucideIcon; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 sm:p-5">
      <h2 id={id} className="flex items-center gap-2 font-display text-lg font-bold">
        <Icon aria-hidden className="size-5" />
        {title}
      </h2>
      {children}
    </section>
  );
}

/** One line (label and value) and a bar below it, the same on phones (AC12). */
function MeterRow({ meter }: { meter: Meter }) {
  const Icon = METER_ICONS[meter.key];
  const percent = meter.limit == null ? 0 : Math.min(100, Math.round(((meter.used ?? 0) / meter.limit) * 100));
  return (
    <li className="flex flex-col gap-1.5">
      <div className="flex min-w-0 items-center gap-2 text-sm">
        <Icon aria-hidden className="size-4 shrink-0" />
        <span className="min-w-0 flex-1 truncate">{METER_LABELS[meter.key]}</span>
        <span className="shrink-0 tabular-nums text-text-secondary">{meterValue(meter)}</span>
      </div>
      {meter.limit != null && (
        <>
          <div
            role="progressbar"
            aria-label={METER_LABELS[meter.key]}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
            aria-valuetext={meterValue(meter)}
            className="h-1.5 w-full overflow-hidden rounded-pill bg-muted"
          >
            <div className="h-full rounded-pill bg-primary" style={{ width: `${String(percent)}%` }} />
          </div>
          <p className="text-xs text-text-secondary">{resetLabel(meter)}</p>
        </>
      )}
    </li>
  );
}

function DeleteAccount({ email, onDeleted }: { email: string; onDeleted: () => void }) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const inputId = useId();
  const remove = useMutation({
    mutationFn: () => deleteAccount(typed),
    onSuccess: onDeleted,
  });
  const matches = typed.trim().toLowerCase() === email.toLowerCase();
  return (
    <>
      <button type="button" onClick={() => { setOpen(true); }} className={`${buttonSecondary} ${DESTRUCTIVE}`}>
        <Trash2 aria-hidden className="size-4" />
        Delete account
      </button>
      <Dialog
        open={open}
        title="Delete your account?"
        onClose={() => { setOpen(false); setTyped(""); remove.reset(); }}
        footer={
          <>
            <button type="button" onClick={() => { setOpen(false); setTyped(""); }} className={buttonSecondary}>
              Cancel
            </button>
            <button
              type="button"
              disabled={!matches || remove.isPending}
              onClick={() => { remove.mutate(); }}
              className={`${buttonSecondary} ${DESTRUCTIVE} disabled:opacity-50`}
            >
              Delete everything
            </button>
          </>
        }
      >
        <p className="text-sm">
          This removes every paper, summary, conversation, collection and template you have. It cannot be undone.
        </p>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={inputId} className="text-sm font-medium">{`Type ${email} to confirm`}</label>
          <input
            id={inputId}
            type="email"
            autoComplete="off"
            value={typed}
            onChange={(e) => { setTyped(e.target.value); }}
            className={inputClass}
          />
          <FieldError id={`${inputId}-error`} message={remove.isError ? remove.error.message : null} />
        </div>
      </Dialog>
    </>
  );
}

/** Settings (spec 012 AC11 to AC16): profile, plan and usage, appearance, account. */
export function SettingsPage() {
  const auth = useAuthState();
  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const usage = useQuery({ queryKey: settingsKeys.usage, queryFn: getUsage });
  const name = me.data?.user.display_name ?? me.data?.user.email ?? "";
  const email = me.data?.user.email ?? "";

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-4 pt-4 pb-28 sm:pt-6 md:px-8 lg:pb-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Settings</h1>
        <p className="mt-1 hidden text-text-secondary sm:block">Your account, plan and appearance.</p>
      </header>

      <Section title="Profile" icon={User}>
        {me.isPending ? (
          <Loading label="Loading your profile"><ListRowSkeleton /></Loading>
        ) : (
          <div className="flex min-w-0 items-center gap-3">
            <span aria-hidden className="inline-flex size-12 shrink-0 items-center justify-center rounded-pill bg-muted font-medium">
              {initials(name)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium" title={name}>{name}</p>
              <p className="truncate text-sm text-text-secondary" title={email}>{email}</p>
            </div>
          </div>
        )}
        <p className="text-xs text-text-secondary">Your name and email come from your sign-in account.</p>
      </Section>

      <Section title="Plan and usage" icon={BarChart3}>
        {usage.isPending ? (
          <Loading label="Loading your usage"><ListRowSkeleton /><ListRowSkeleton /></Loading>
        ) : usage.isError ? (
          <p role="alert" className="text-sm">
            {usage.error.message}{" "}
            <button type="button" onClick={() => void usage.refetch()} className="min-h-11 underline">Try again</button>
          </p>
        ) : (
          <>
            <p className="text-sm">
              {"You are on the "}
              <span className="font-medium">{usage.data.plan.name}</span>
              {" plan."}
            </p>
            <ul aria-label="Usage" className="flex flex-col gap-4">
              {usage.data.meters.map((m) => <MeterRow key={m.key} meter={m} />)}
            </ul>
          </>
        )}
      </Section>

      <Section title="Appearance" icon={Palette}>
        <div className="self-start">
          <ThemeToggle />
        </div>
      </Section>

      <Section title="Account" icon={LogOut}>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => { auth.signOut(); }} className={buttonSecondary}>
            <LogOut aria-hidden className="size-4" />
            Sign out
          </button>
          {email && (
            <DeleteAccount
              email={email}
              onDeleted={() => {
                toast("Your account is deleted. Your files are being removed.");
                auth.signOut();
              }}
            />
          )}
        </div>
      </Section>
    </div>
  );
}
