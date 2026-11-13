import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { Dialog, buttonPrimary, buttonSecondary } from "@/components/dialog/Dialog";
import { ListRowSkeleton, Loading } from "@/components/feedback/Skeleton";
import { StatusPill } from "@/components/status/StatusPill";
import { toast } from "@/components/status/toast";

import { adminKeys, getOverview, setKillSwitch, setPlatformCap, type Overview } from "./api";
import { OverviewCharts } from "./OverviewCharts";
import { count, money } from "./format";
import { Card, NumberField, Switch } from "./ui";

function Stat({ label, value, detail, to }: { label: string; value: string; detail?: string; to?: "/app/admin/jobs" }) {
  const body = (
    <>
      <span className="truncate text-sm text-text-secondary">{label}</span>
      <span className="font-display text-2xl font-bold tabular-nums">{value}</span>
      {detail && <span className="truncate text-xs text-text-secondary">{detail}</span>}
    </>
  );
  const cls = "flex min-w-0 flex-col gap-0.5 rounded-lg border border-border bg-surface p-4";
  // Each card opens its detail where there is one (spec 018 AC4).
  return to ? <Link to={to} className={`${cls} hover:bg-muted/50`}>{body}</Link> : <div className={cls}>{body}</div>;
}

function Rows({ label, rows }: { label: string; rows: { key: string; name: string; value: string; detail?: string }[] }) {
  if (rows.length === 0) return <p className="text-sm text-text-secondary">Nothing yet.</p>;
  return (
    <ul aria-label={label} className="flex flex-col divide-y divide-border">
      {rows.map((r) => (
        <li key={r.key} className="flex min-w-0 items-center gap-3 py-2 text-sm">
          <span className="min-w-0 flex-1 truncate">{r.name}</span>
          {r.detail && <span className="hidden shrink-0 text-text-secondary sm:inline">{r.detail}</span>}
          <span className="shrink-0 tabular-nums">{r.value}</span>
        </li>
      ))}
    </ul>
  );
}

function SpendCard({ data }: { data: Overview }) {
  const queryClient = useQueryClient();
  const [cap, setCap] = useState<number | null>(data.cap_usd);
  const save = useMutation({
    mutationFn: () => setPlatformCap(cap ?? 0),
    onSuccess: async () => {
      toast("Daily cap saved.");
      await queryClient.invalidateQueries({ queryKey: adminKeys.overview });
    },
    onError: (e) => { toast(e.message); },
  });
  const percent = data.cap_usd > 0 ? Math.min(100, Math.round((data.spend_today_usd / data.cap_usd) * 100)) : 100;
  return (
    <Card title="Daily cap" action={data.cap_warning ? <StatusPill status="warning">Over 80% of the cap</StatusPill> : undefined}>
      {/* Today's amount is on the summary card above (say it once); this card is the cap. */}
      <p className="text-sm text-text-secondary">{`${String(percent)}% of ${money(data.cap_usd)} used today`}</p>
      <div role="progressbar" aria-label="Spend today against the daily cap" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} className="h-1.5 overflow-hidden rounded-pill bg-muted">
        <div className="h-full rounded-pill bg-primary" style={{ width: `${String(percent)}%` }} />
      </div>
      <div className="flex items-end gap-2">
        <div className="w-40">
          <NumberField label="Daily cap (USD)" value={cap} onChange={setCap} step="money" />
        </div>
        <button type="button" disabled={save.isPending || cap === data.cap_usd || cap === null || cap < 0} onClick={() => { save.mutate(); }} className={buttonSecondary}>
          Save cap
        </button>
      </div>
    </Card>
  );
}

function KillSwitchCard({ enabled }: { enabled: boolean }) {
  const queryClient = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const change = useMutation({
    mutationFn: (next: boolean) => setKillSwitch(next),
    onSuccess: async (_d, next) => {
      setConfirm(false);
      toast(next ? "AI calls resumed." : "All paid AI calls are paused.");
      await queryClient.invalidateQueries({ queryKey: adminKeys.overview });
    },
    onError: (e) => { toast(e.message); },
  });
  return (
    <Card title="AI calls" action={<Switch label="Paid AI calls" checked={enabled} onChange={() => { setConfirm(true); }} />}>
      <p className="text-sm text-text-secondary">
        {enabled ? "Paid AI calls are running." : "Paused: summaries and answers wait until calls resume."}
      </p>
      <Dialog
        open={confirm}
        title={enabled ? "Pause all paid AI calls?" : "Resume paid AI calls?"}
        onClose={() => { setConfirm(false); }}
        footer={
          <>
            <button type="button" onClick={() => { setConfirm(false); }} className={buttonSecondary}>Cancel</button>
            <button type="button" disabled={change.isPending} onClick={() => { change.mutate(!enabled); }} className={buttonPrimary}>
              {enabled ? "Pause" : "Resume"}
            </button>
          </>
        }
      >
        <p className="text-sm">
          {enabled ? "Everyone's summaries and answers stop until you resume. Use this if spend runs away." : "Summaries and answers start again for everyone."}
        </p>
      </Dialog>
    </Card>
  );
}

/** Admin overview (spec 011 AC3, AC4, AC13): spend, cap, usage, top users, health. */
export function OverviewPage() {
  const overview = useQuery({ queryKey: adminKeys.overview, queryFn: getOverview, refetchInterval: 30_000 });
  if (overview.isPending) return <Loading label="Loading the overview"><ListRowSkeleton /><ListRowSkeleton /></Loading>;
  if (overview.isError) return <p role="alert">{overview.error.message}</p>;
  const d = overview.data;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Spend today"
          value={money(d.spend_today_usd)}
          detail={`of ${money(d.cap_usd)} a day`}
        />
        <Stat label="Spend this month" value={money(d.spend_month_usd)} />
        <Stat label="Tokens today" value={count(d.tokens_today)} />
        <Stat
          label="Failed jobs"
          value={count(d.jobs.failed_24h ?? 0)}
          detail={`Last 24 hours, ${count((d.jobs.queued ?? 0) + (d.jobs.held ?? 0))} waiting, ${count(d.jobs.running ?? 0)} running`}
          to="/app/admin/jobs"
        />
      </div>
      <OverviewCharts capUsd={d.cap_usd} />
      <div className="grid items-start gap-4 lg:grid-cols-2">
        <SpendCard key={d.cap_usd} data={d} />
        <KillSwitchCard enabled={d.paid_calls_enabled} />
        <Card title="Top users today">
          <Rows label="Top users today" rows={d.top_today.map((u) => ({ key: u.user_id, name: u.email ?? u.display_name ?? "Unknown", value: money(u.spend_usd), detail: `${count(u.calls)} calls` }))} />
        </Card>
        <Card title="Top users this month">
          <Rows label="Top users this month" rows={d.top_month.map((u) => ({ key: u.user_id, name: u.email ?? u.display_name ?? "Unknown", value: money(u.spend_usd), detail: `${count(u.calls)} calls` }))} />
        </Card>
        <Card title="By task this month">
          <Rows label="By task" rows={d.by_task.map((t) => ({ key: t.name, name: t.name, value: money(t.cost_usd), detail: `${count(t.calls)} calls, ${count(t.tokens)} tokens` }))} />
        </Card>
        <Card title="By model this month">
          <Rows label="By model" rows={d.by_model.map((t) => ({ key: t.name, name: t.name, value: money(t.cost_usd), detail: `${count(t.calls)} calls` }))} />
        </Card>
        <Card title="Queues">
          {d.queues ? (
            <Rows label="Queues" rows={Object.entries(d.queues).map(([name, depth]) => ({ key: name, name, value: count(depth) }))} />
          ) : (
            <p className="text-sm text-text-secondary">Queue depth is unavailable right now.</p>
          )}
        </Card>
        <Card title="AI errors, last 24 hours" action={<Link to="/app/admin/jobs" className="min-h-11 py-2 text-sm underline">Jobs</Link>}>
          <Rows
            label="AI errors by provider"
            rows={d.provider_errors.map((p) => ({ key: p.provider, name: p.provider, value: p.calls ? `${String(Math.round((p.errors / p.calls) * 100))}%` : "0%", detail: `${count(p.errors)} of ${count(p.calls)} calls` }))}
          />
        </Card>
      </div>
    </div>
  );
}
