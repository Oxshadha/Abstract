import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Loading } from "@/components/feedback/Skeleton";

import { adminKeys, getOverviewSeries, type OverviewSeries } from "./api";
import { BarChart, Donut, RangeSwitch, type RangeKey, type Series, type Slice } from "./charts";
import { count, money, shortDate } from "./format";
import { Card } from "./ui";

const KEY = "abstract.admin.range";
const RANGE_DAYS: Record<RangeKey, number> = { "7d": 7, "30d": 30, "90d": 90 };
const MAX_PROVIDERS = 3;

function savedRange(): RangeKey {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === "7d" || v === "90d" ? v : "30d";
  } catch {
    return "30d";
  }
}

/** "highest $4.10 on 2 Nov" for the accessible summary. */
function peakText(dates: string[], values: number[], format: (n: number) => string): string {
  let best = -1;
  values.forEach((v, i) => { if (v > 0 && (best < 0 || v > (values[best] ?? 0))) best = i; });
  return best < 0 ? "nothing yet" : `highest ${format(values[best] ?? 0)} on ${shortDate(dates[best] ?? "")}`;
}

function ChartSkeleton() {
  return <div aria-hidden className="h-[180px] animate-pulse rounded-md bg-muted" />;
}

/** AI errors per day, stacked by provider: the busiest three, then Other. */
function errorSeries(data: OverviewSeries): Series[] {
  const totals = new Map<string, number>();
  for (const d of data.days) for (const [p, n] of Object.entries(d.errors)) totals.set(p, (totals.get(p) ?? 0) + n);
  const top = [...totals.entries()].sort((a, b) => b[1] - a[1]).slice(0, MAX_PROVIDERS).map(([p]) => p);
  const series: Series[] = top.map((p) => ({ key: p, label: p, values: data.days.map((d) => d.errors[p] ?? 0) }));
  const rest = data.days.map((d) => Object.entries(d.errors).reduce((s, [p, n]) => (top.includes(p) ? s : s + n), 0));
  if (rest.some((v) => v > 0)) series.push({ key: "other", label: "Other", values: rest });
  return series.length ? series : [{ key: "none", label: "Errors", values: data.days.map(() => 0) }];
}

const JOB_LABELS: Record<string, string> = { queued: "Queued", running: "Running", succeeded: "Succeeded", failed: "Failed", enqueue_failed: "Could not queue" };

/**
 * The Overview charts (spec 018 AC5 to AC8, AC11): spend and activity per day, and where the
 * money and jobs go. A failed request shows a Retry here and leaves the rest of the page alone.
 */
export function OverviewCharts({ capUsd }: { capUsd: number }) {
  const [range, setRange] = useState<RangeKey>(savedRange);
  const [donut, setDonut] = useState<"task" | "model">("task");
  const series = useQuery({ queryKey: adminKeys.series(range), queryFn: () => getOverviewSeries(range), refetchInterval: 60_000 });

  const changeRange = (next: RangeKey) => {
    setRange(next);
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      // private mode: back to 30 days next visit
    }
  };

  const span = `last ${String(RANGE_DAYS[range])} days`;
  const header = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="font-display text-lg font-bold">Activity</h2>
      <RangeSwitch value={range} onChange={changeRange} />
    </div>
  );

  if (series.isPending) {
    return (
      <section aria-label="Activity" className="flex flex-col gap-4">
        {header}
        <Loading label="Loading the charts">
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2"><ChartSkeleton /></div>
            <ChartSkeleton />
          </div>
        </Loading>
      </section>
    );
  }
  if (series.isError) {
    return (
      <section aria-label="Activity" className="flex flex-col gap-4">
        {header}
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-4 text-sm">
          <span>{series.error.message}</span>
          <button type="button" onClick={() => { void series.refetch(); }} className="inline-flex min-h-11 items-center rounded-pill border border-border px-4 font-medium hover:bg-muted">
            Retry
          </button>
        </div>
      </section>
    );
  }

  const d = series.data;
  const dates = d.days.map((x) => x.date);
  const spend = d.days.map((x) => x.spend_usd);
  const papers = d.days.map((x) => x.papers);
  const questions = d.days.map((x) => x.questions);
  const signups = d.days.map((x) => x.signups);
  const active = d.days.map((x) => x.active_users);
  const errors = errorSeries(d);
  const errorTotals = dates.map((_, i) => errors.reduce((s, e) => s + (e.values[i] ?? 0), 0));
  const near = capUsd > 0 ? capUsd * 0.8 : Infinity;
  const money$ = d.by_task.length || d.by_model.length;
  const slices = (donut === "task" ? d.by_task : d.by_model).map((s) => ({ name: s.name, value: s.value }));
  const jobs: Slice[] = Object.entries(d.jobs_by_state).map(([k, v]) => ({
    name: JOB_LABELS[k] ?? k,
    value: v,
    to: k === "failed" || k === "enqueue_failed" ? "/app/admin/jobs" : undefined,
  }));
  const plans: Slice[] = Object.entries(d.users_by_plan).map(([k, v]) => ({ name: k.charAt(0).toUpperCase() + k.slice(1), value: v, to: "/app/admin/plans" }));
  const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

  return (
    <section aria-label="Activity" className="flex flex-col gap-4">
      {header}
      {/* Two columns that fill on their own: bars on the left, breakdowns on the right. */}
      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-4 lg:col-span-2">
          <Card title="Spend per day">
            <BarChart
              summary={`Spend per day, ${span}, ${peakText(dates, spend, money)}, total ${money(sum(spend))}`}
              dates={dates}
              series={[{ key: "spend", label: "Spend", values: spend }]}
              format={money}
              line={capUsd > 0 ? { value: capUsd, label: `Cap ${money(capUsd)}` } : undefined}
              flagged={(i) => ((spend[i] ?? 0) >= near ? "At or over 80% of the cap" : null)}
            />
          </Card>
          <Card title="Papers and questions per day">
            <BarChart
              summary={`Papers and questions per day, ${span}: ${count(sum(papers))} papers, ${count(sum(questions))} questions`}
              dates={dates}
              series={[{ key: "papers", label: "Papers", values: papers }, { key: "questions", label: "Questions", values: questions }]}
              format={count}
            />
          </Card>
          <Card title="Active users per day">
            <BarChart summary={`Active users per day, ${span}, ${peakText(dates, active, count)}`} dates={dates} series={[{ key: "active", label: "Active users", values: active }]} format={count} />
          </Card>
          <Card title="AI errors per day">
            <BarChart summary={`AI errors per day by provider, ${span}, ${count(sum(errorTotals))} in total`} dates={dates} series={errors} stacked format={count} />
          </Card>
          <Card title="New sign-ups per day">
            <BarChart summary={`New sign-ups per day, ${span}, ${count(sum(signups))} in total`} dates={dates} series={[{ key: "signups", label: "Sign-ups", values: signups }]} format={count} />
          </Card>
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <Card
            title={donut === "task" ? "Spend by task" : "Spend by model"}
            action={
              money$ ? (
                <div role="radiogroup" aria-label="Group spend by" className="inline-flex rounded-pill border border-border p-0.5 text-xs">
                  {(["task", "model"] as const).map((k) => (
                    <button key={k} type="button" role="radio" aria-checked={donut === k} onClick={() => { setDonut(k); }} className={`min-h-8 rounded-pill px-2.5 ${donut === k ? "bg-primary text-primary-text" : "text-text-secondary"}`}>
                      {k === "task" ? "Task" : "Model"}
                    </button>
                  ))}
                </div>
              ) : undefined
            }
          >
            <Donut summary={`Spend by ${donut}, ${span}, total ${money(sum(slices.map((s) => s.value)))}`} slices={slices} format={money} total="spent" />
          </Card>
          <Card title="Jobs by state">
            <Donut summary={`Jobs by state, ${span}, ${count(sum(jobs.map((j) => j.value)))} jobs`} slices={jobs} format={count} total="jobs" />
          </Card>
          <Card title="Users by plan">
            <Donut summary={`Users by plan, ${count(sum(plans.map((p) => p.value)))} users`} slices={plans} format={count} total="users" />
          </Card>
        </div>
      </div>
    </section>
  );
}
