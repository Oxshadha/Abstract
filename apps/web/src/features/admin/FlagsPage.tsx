import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ListRowSkeleton, Loading } from "@/components/feedback/Skeleton";
import { Select } from "@/components/menu/Select";
import { toast } from "@/components/status/toast";

import { adminKeys, listFlags, listPlans, updateFlag, type Flag } from "./api";
import { Switch } from "./ui";

type Who = Flag["audience"]["who"];
const NAMES: Record<string, string> = { figures: "Figures & tables", search: "Search", reading_aids: "Reading aids" };

function FlagRow({ flag, planIds }: { flag: Flag; planIds: { value: string; label: string }[] }) {
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: (next: { enabled: boolean; audience: Flag["audience"] }) => updateFlag(flag.key, next.enabled, next.audience),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminKeys.flags });
      await queryClient.invalidateQueries({ queryKey: ["me", "flags"] });
    },
    onError: (e) => { toast(e.message); },
  });
  const name = NAMES[flag.key] ?? flag.key;
  const audienceOptions: { value: string; label: string }[] = [
    { value: "everyone", label: "Everyone" },
    { value: "admins", label: "Admins only" },
    ...planIds.map((p) => ({ value: `plan:${p.value}`, label: `${p.label} plan` })),
  ];
  const current = flag.audience.who === "plans" ? `plan:${flag.audience.plans?.[0] ?? ""}` : flag.audience.who;
  return (
    <li className="flex min-w-0 items-center gap-3 py-3">
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{name}</p>
        <p className="truncate text-xs text-text-secondary" title={flag.description}>{flag.description}</p>
      </div>
      <Select
        label={`Who sees ${name}`}
        value={current}
        options={audienceOptions}
        width="w-40"
        compact
        onChange={(v) => {
          const audience = v.startsWith("plan:")
            ? { who: "plans" as Who, plans: [v.slice(5)] }
            : { who: v as Who, plans: [] };
          save.mutate({ enabled: flag.enabled, audience });
        }}
      />
      <Switch label={name} checked={flag.enabled} disabled={save.isPending} onChange={(on) => { save.mutate({ enabled: on, audience: flag.audience }); }} />
    </li>
  );
}

/** Admin flags (spec 011 AC6, AC7): on or off, for everyone, admins, or one plan; audited. */
export function FlagsPage() {
  const flags = useQuery({ queryKey: adminKeys.flags, queryFn: listFlags });
  const plans = useQuery({ queryKey: adminKeys.plans, queryFn: listPlans });
  if (flags.isPending) return <Loading label="Loading flags"><ListRowSkeleton /></Loading>;
  if (flags.isError) return <p role="alert">{flags.error.message}</p>;
  const planIds = (plans.data ?? []).map((p) => ({ value: p.id, label: p.name }));
  return (
    <ul aria-label="Feature flags" className="flex flex-col divide-y divide-border rounded-lg border border-border bg-surface px-4">
      {flags.data.map((f) => <FlagRow key={f.key} flag={f} planIds={planIds} />)}
    </ul>
  );
}
