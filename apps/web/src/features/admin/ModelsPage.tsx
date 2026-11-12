import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useId, useState } from "react";

import { Dialog, buttonPrimary, buttonSecondary, inputClass } from "@/components/dialog/Dialog";
import { ListRowSkeleton, Loading } from "@/components/feedback/Skeleton";
import { Select } from "@/components/menu/Select";
import { FieldError } from "@/components/status/FieldError";
import { StatusPill } from "@/components/status/StatusPill";
import { toast } from "@/components/status/toast";
import { HttpError } from "@/lib/queryClient";

import { adminKeys, listModels, updateModel, type ModelEntry, type ModelUpdate } from "./api";
import { NumberField, Switch } from "./ui";

type Route = ModelEntry["routes"][number];
const PROVIDERS: { value: Route["provider"]; label: string }[] = [
  { value: "vertex", label: "Vertex AI" },
  { value: "openrouter", label: "OpenRouter" },
  { value: "fake", label: "Fake (tests)" },
];

function RouteRow({ route, index, onChange, onRemove }: { route: Route; index: number; onChange: (r: Route) => void; onRemove?: () => void }) {
  const modelId = useId();
  const name = index === 0 ? "Primary" : `Fallback ${String(index)}`;
  return (
    <li className="flex flex-col gap-2 rounded-md border border-border p-3">
      <div className="flex items-center gap-2">
        <span className="flex-1 text-sm font-medium">{name}</span>
        {onRemove && (
          <button type="button" aria-label={`Remove ${name}`} onClick={onRemove} className="inline-flex size-9 items-center justify-center rounded-md hover:bg-muted">
            <Trash2 aria-hidden className="size-4" />
          </button>
        )}
      </div>
      <div className="grid gap-2 sm:grid-cols-[10rem_1fr]">
        <Select label={`${name} provider`} value={route.provider} options={PROVIDERS} onChange={(provider) => { onChange({ ...route, provider }); }} width="w-40" />
        <div>
          <label htmlFor={modelId} className="sr-only">{`${name} model`}</label>
          <input id={modelId} value={route.model} onChange={(e) => { onChange({ ...route, model: e.target.value }); }} placeholder="Model id" className={inputClass} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <NumberField label="Input USD per million" value={route.input_usd_per_m} onChange={(v) => { onChange({ ...route, input_usd_per_m: v ?? 0 }); }} step="money" />
        <NumberField label="Output USD per million" value={route.output_usd_per_m} onChange={(v) => { onChange({ ...route, output_usd_per_m: v ?? 0 }); }} step="money" />
      </div>
    </li>
  );
}

function EditModel({ entry, onClose }: { entry: ModelEntry; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<ModelUpdate>({
    routes: entry.routes,
    params: entry.params,
    deadline_seconds: entry.deadline_seconds,
    on_budget: entry.on_budget,
    enabled: entry.enabled,
    confirm_reindex: false,
  });
  const [needsReindex, setNeedsReindex] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (confirm: boolean) => updateModel(entry.task, entry.version, { ...draft, confirm_reindex: confirm }),
    onSuccess: async () => {
      toast(`Saved. ${entry.task} uses it from the next call.`);
      await queryClient.invalidateQueries({ queryKey: adminKeys.models });
      onClose();
    },
    onError: (e) => {
      if (e instanceof HttpError && e.status === 409) setNeedsReindex(e.message);
    },
  });
  const setRoute = (i: number) => (r: Route) => { setDraft((d) => ({ ...d, routes: d.routes.map((x, j) => (j === i ? r : x)) })); };
  return (
    <Dialog
      open
      title={`Model for ${entry.task}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} className={buttonSecondary}>Cancel</button>
          {needsReindex ? (
            <button type="button" disabled={save.isPending} onClick={() => { save.mutate(true); }} className={buttonPrimary}>Save and re-index</button>
          ) : (
            <button type="button" disabled={save.isPending || draft.routes.some((r) => !r.model.trim())} onClick={() => { save.mutate(false); }} className={buttonPrimary}>Save</button>
          )}
        </>
      }
    >
      <div className="flex max-h-[60vh] flex-col gap-3 overflow-y-auto">
        <ul aria-label="Models in order" className="flex flex-col gap-2">
          {draft.routes.map((r, i) => (
            <RouteRow key={i} route={r} index={i} onChange={setRoute(i)} onRemove={i > 0 ? () => { setDraft((d) => ({ ...d, routes: d.routes.filter((_, j) => j !== i) })) } : undefined} />
          ))}
        </ul>
        {draft.routes.length < 5 && (
          <button type="button" onClick={() => { setDraft((d) => ({ ...d, routes: [...d.routes, { provider: "openrouter", model: "", input_usd_per_m: 0, output_usd_per_m: 0 }] })); }} className={`${buttonSecondary} self-start`}>
            <Plus aria-hidden className="size-4" />
            Add fallback
          </button>
        )}
        <div className="grid grid-cols-2 gap-2">
          <NumberField label="Max tokens" value={draft.params.max_tokens} onChange={(v) => { setDraft((d) => ({ ...d, params: { ...d.params, max_tokens: v ?? 1 } })); }} />
          <NumberField label="Deadline (seconds)" value={draft.deadline_seconds} onChange={(v) => { setDraft((d) => ({ ...d, deadline_seconds: v ?? 1 })); }} step="money" />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Select
            label="At the budget cap"
            value={draft.on_budget}
            options={[{ value: "downgrade", label: "Use the cheapest model" }, { value: "stop", label: "Stop" }]}
            onChange={(v) => { setDraft((d) => ({ ...d, on_budget: v })); }}
            width="w-56"
          />
          <span className="flex items-center gap-1 text-sm">
            <Switch label="Task enabled" checked={draft.enabled} onChange={(on) => { setDraft((d) => ({ ...d, enabled: on })); }} />
            Enabled
          </span>
        </div>
        {needsReindex && <p className="rounded-md bg-muted p-3 text-sm">{needsReindex}</p>}
        <FieldError id={`model-${entry.task}-error`} message={save.isError && !needsReindex ? save.error.message : null} />
      </div>
    </Dialog>
  );
}

/** Admin models (spec 011 AC10): each task's model chain, limits and budget behaviour. */
export function ModelsPage() {
  const models = useQuery({ queryKey: adminKeys.models, queryFn: listModels });
  const [editing, setEditing] = useState<ModelEntry | null>(null);
  if (models.isPending) return <Loading label="Loading models"><ListRowSkeleton /></Loading>;
  if (models.isError) return <p role="alert">{models.error.message}</p>;
  return (
    <>
      <ul aria-label="Model Registry" className="flex flex-col divide-y divide-border rounded-lg border border-border bg-surface px-4">
        {models.data.map((m) => (
          <li key={m.task} className="flex min-w-0 items-center gap-3 py-3">
            <div className="min-w-0 flex-1">
              <p className="flex min-w-0 items-center gap-2">
                <span className="truncate font-medium">{m.task}</span>
                {!m.enabled && <StatusPill status="neutral">Off</StatusPill>}
              </p>
              <p className="truncate text-xs text-text-secondary">
                {`${m.routes[0]?.model ?? ""}${m.routes.length > 1 ? `, then ${m.routes.slice(1).map((r) => r.model).join(", ")}` : ""} · version ${String(m.version)}`}
              </p>
            </div>
            <button type="button" aria-label={`Edit ${m.task}`} onClick={() => { setEditing(m); }} className="inline-flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-muted">
              <Pencil aria-hidden className="size-5" />
            </button>
          </li>
        ))}
      </ul>
      {editing && <EditModel key={`${editing.task}:${String(editing.version)}`} entry={editing} onClose={() => { setEditing(null); }} />}
    </>
  );
}
