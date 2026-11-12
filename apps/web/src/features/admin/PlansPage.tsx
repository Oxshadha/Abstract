import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { buttonPrimary } from "@/components/dialog/Dialog";
import { ListRowSkeleton, Loading } from "@/components/feedback/Skeleton";
import { toast } from "@/components/status/toast";

import { adminKeys, listPlans, updatePlan, type Plan, type PlanLimits } from "./api";
import { count } from "./format";
import { Card, NumberField } from "./ui";

const RATE_GROUPS = ["read", "write", "upload", "search"] as const;
const FREE_RATES = { read: 300, write: 60, upload: 20, search: 120 };
const RATE_LABELS: Record<(typeof RATE_GROUPS)[number], string> = { read: "Read", write: "Write", upload: "Upload", search: "Search" };

/** The API returns rates as a map; the edit form uses the four known groups. */
function editable(limits: Plan["limits"]): PlanLimits {
  const rates = limits.rate_per_minute;
  return {
    ...limits,
    rate_per_minute: rates
      ? { read: rates.read ?? FREE_RATES.read, write: rates.write ?? FREE_RATES.write, upload: rates.upload ?? FREE_RATES.upload, search: rates.search ?? FREE_RATES.search }
      : null,
  };
}

function PlanCard({ plan }: { plan: Plan }) {
  const queryClient = useQueryClient();
  const [limits, setLimits] = useState<PlanLimits>(() => editable(plan.limits));
  const set = <K extends keyof PlanLimits>(key: K) => (value: PlanLimits[K]) => { setLimits((l) => ({ ...l, [key]: value })); };
  const save = useMutation({
    mutationFn: () => updatePlan(plan.id, limits),
    onSuccess: async () => {
      toast(`${plan.name} plan saved. It applies within seconds.`);
      await queryClient.invalidateQueries({ queryKey: adminKeys.plans });
    },
    onError: (e) => { toast(e.message); },
  });
  const changed = JSON.stringify(limits) !== JSON.stringify(editable(plan.limits));
  return (
    <Card title={plan.name} action={<span className="text-sm text-text-secondary">{`${count(plan.users)} ${plan.users === 1 ? "account" : "accounts"}`}</span>}>
      <p className="text-xs text-text-secondary">Leave a box empty for no limit.</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <NumberField label="Papers a month" value={limits.papers_per_month} onChange={set("papers_per_month")} allowEmpty />
        <NumberField label="Questions a day" value={limits.messages_per_day} onChange={set("messages_per_day")} allowEmpty />
        <NumberField label="Papers at once" value={limits.concurrent_jobs} onChange={set("concurrent_jobs")} allowEmpty />
        <NumberField label="AI a day (USD)" value={limits.ai_usd_per_day} onChange={set("ai_usd_per_day")} allowEmpty step="money" />
        <NumberField label="AI a month (USD)" value={limits.ai_usd_per_month} onChange={set("ai_usd_per_month")} allowEmpty step="money" />
        <NumberField label="Fields per template" value={limits.fields_per_template} onChange={(v) => { set("fields_per_template")(v ?? 1); }} />
        <NumberField label="Custom templates" value={limits.custom_templates} onChange={(v) => { set("custom_templates")(v ?? 1); }} />
      </div>
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-xs text-text-secondary">Requests a minute (empty: no limit)</legend>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {RATE_GROUPS.map((g) => (
            <NumberField
              key={g}
              label={RATE_LABELS[g]}
              value={limits.rate_per_minute?.[g] ?? null}
              allowEmpty
              onChange={(v) => {
                setLimits((l) => {
                  if (v === null) return { ...l, rate_per_minute: null };
                  return { ...l, rate_per_minute: { ...(l.rate_per_minute ?? FREE_RATES), [g]: v } };
                });
              }}
            />
          ))}
        </div>
      </fieldset>
      <div>
        <button type="button" disabled={!changed || save.isPending} onClick={() => { save.mutate(); }} className={buttonPrimary}>
          Save
        </button>
      </div>
    </Card>
  );
}

/** Admin plans (spec 011 AC12): limits editable, validated by the API, audited. */
export function PlansPage() {
  const plans = useQuery({ queryKey: adminKeys.plans, queryFn: listPlans });
  if (plans.isPending) return <Loading label="Loading plans"><ListRowSkeleton /></Loading>;
  if (plans.isError) return <p role="alert">{plans.error.message}</p>;
  return (
    <div className="grid items-start gap-4 xl:grid-cols-2">
      {plans.data.map((p) => <PlanCard key={`${p.id}:${JSON.stringify(p.limits)}`} plan={p} />)}
    </div>
  );
}
