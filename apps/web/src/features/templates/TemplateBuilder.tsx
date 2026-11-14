import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useBlocker, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, Download, Loader2, Play, Plus, Upload } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { Dialog, buttonPrimary, buttonSecondary, inputClass } from "@/components/dialog/Dialog";
import { Loading, SummaryCardSkeleton } from "@/components/feedback/Skeleton";
import { Select } from "@/components/menu/Select";
import { FieldError } from "@/components/status/FieldError";
import { toast } from "@/components/status/toast";
import { libraryKeys, listLibrary } from "@/features/library/api";

import {
  StaleTemplateError,
  createTemplate,
  getLimits,
  getTemplate,
  previewTemplate,
  saveTemplate,
  templateKeys,
  type Limits,
  type PreviewField,
} from "./api";
import { FieldCard } from "./FieldCard";
import { exportJson, fromTemplate, hasProblems, importJson, newField, toTemplateIn, validate, type Draft } from "./fields";

const DRAFT_PREFIX = "abstract.template-draft.";
const EMPTY: Draft = { name: "", description: "", fields: [newField()] };

function readDraft(key: string): Draft | null {
  try {
    const raw = localStorage.getItem(DRAFT_PREFIX + key);
    return raw ? (JSON.parse(raw) as Draft) : null;
  } catch {
    return null;
  }
}

function writeDraft(key: string, draft: Draft | null) {
  try {
    if (draft) localStorage.setItem(DRAFT_PREFIX + key, JSON.stringify(draft));
    else localStorage.removeItem(DRAFT_PREFIX + key);
  } catch {
    // private mode: the draft lasts for this visit only
  }
}

/** Build or edit a template like a form (spec 010, D36, D41, D87): loads, then shows the form. */
export function TemplateBuilder({ templateId }: { templateId?: string }) {
  const limits = useQuery({ queryKey: templateKeys.limits, queryFn: getLimits, staleTime: 5 * 60_000 });
  const saved = useQuery({
    queryKey: templateKeys.detail(templateId ?? "new"),
    queryFn: () => getTemplate(templateId ?? ""),
    enabled: Boolean(templateId),
  });
  if (limits.isPending || (templateId && saved.isPending)) {
    return (
      <div className="px-4 pt-6 md:px-8">
        <Loading label="Loading the template">
          <SummaryCardSkeleton />
        </Loading>
      </div>
    );
  }
  if (saved.isError) return <div role="alert" className="px-4 pt-6 md:px-8">{saved.error.message}</div>;
  if (limits.isError) return <div role="alert" className="px-4 pt-6 md:px-8">{limits.error.message}</div>;
  const start = saved.data ? fromTemplate(saved.data) : { ...EMPTY, fields: [newField()] };
  return <BuilderForm templateId={templateId} limits={limits.data} initial={start} initialVersion={saved.data?.version ?? 1} />;
}

function BuilderForm({ templateId, limits: limitValues, initial, initialVersion }: { templateId?: string; limits: Limits; initial: Draft; initialVersion: number }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const draftKey = templateId ?? "new";
  const [draft, setDraft] = useState<Draft>(initial);
  const [baseVersion, setBaseVersion] = useState(initialVersion);
  const [dirty, setDirty] = useState(false);
  const [showProblems, setShowProblems] = useState(false);
  const [stale, setStale] = useState<number | null>(null);
  // A newer local draft than the saved template is offered back (AC6).
  const [restore, setRestore] = useState<Draft | null>(() => {
    const local = readDraft(draftKey);
    return local && JSON.stringify(local) !== JSON.stringify(initial) ? local : null;
  });
  const nameId = useId();
  const fileInput = useRef<HTMLInputElement>(null);

  const update = (next: Draft) => {
    setDraft(next);
    setDirty(true);
    writeDraft(draftKey, next);
  };

  // Leaving with unsaved changes asks first (AC6), with the app's own dialog.
  // A ref, not state: Save clears it right before navigating to the saved template, and the
  // blocker must see that at once (state would still read "dirty" in this render).
  const dirtyRef = useRef(false);
  useEffect(() => {
    dirtyRef.current = dirty;
  }, [dirty]);
  const blocker = useBlocker({ shouldBlockFn: () => dirtyRef.current, withResolver: true, enableBeforeUnload: () => dirtyRef.current });

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const problems = useMemo(() => validate(draft, limitValues), [draft, limitValues]);
  const atLimit = draft.fields.length >= limitValues.fields_per_template;

  const save = useMutation({
    mutationFn: async (overrideBase?: number) => {
      const body = toTemplateIn(draft);
      return templateId ? saveTemplate(templateId, overrideBase ?? baseVersion, body) : createTemplate(body);
    },
    onSuccess: async (t) => {
      writeDraft(draftKey, null);
      dirtyRef.current = false;
      setDirty(false);
      setBaseVersion(t.version);
      setDraft(fromTemplate(t));
      void client.invalidateQueries({ queryKey: templateKeys.list });
      client.setQueryData(templateKeys.detail(t.id), t);
      toast(templateId ? `Saved as version ${String(t.version)}.` : "Template created.");
      if (!templateId) {
        await navigate({ to: "/app/templates/$templateId", params: { templateId: t.id }, replace: true });
      }
    },
    onError: (err) => {
      if (err instanceof StaleTemplateError) setStale(err.currentVersion);
      else toast.error(err.message);
    },
  });

  const submit = () => {
    setShowProblems(true);
    if (hasProblems(problems)) return;
    save.mutate(undefined);
  };

  // Try on a paper (AC7): one run, streamed; nothing is saved.
  const papers = useQuery({
    queryKey: libraryKeys.list({ sort: "opened" }),
    queryFn: ({ signal }) => listLibrary({ sort: "opened" }, null, signal),
    select: (page) => page.items.filter((p) => p.status === "ready"),
  });
  const [paperId, setPaperId] = useState<string>("");
  const [preview, setPreview] = useState<PreviewField[] | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const previewAbort = useRef<AbortController | null>(null);
  useEffect(() => () => previewAbort.current?.abort(), []);
  const runPreview = async () => {
    setShowProblems(true);
    if (hasProblems(problems)) return;
    const target = paperId || papers.data?.[0]?.id;
    if (!target) return;
    previewAbort.current?.abort();
    const abort = new AbortController();
    previewAbort.current = abort;
    setPreview([]);
    setPreviewing(true);
    try {
      await previewTemplate(target, toTemplateIn(draft), (field) => { setPreview((list) => [...(list ?? []), field]); }, abort.signal);
    } catch (err) {
      if (!abort.signal.aborted) toast.error(err instanceof Error ? err.message : "Could not run the preview.");
    } finally {
      setPreviewing(false);
    }
  };

  const max = limitValues.fields_per_template;
  const labelsByKey = new Map(draft.fields.map((f) => [f.key ?? "", f.label]));

  return (
    <div className="flex flex-col gap-4 px-4 pt-3 pb-10 sm:pt-6 md:px-8">
      <header className="flex items-center gap-2">
        <Link to="/app/templates" aria-label="Back to templates" className="inline-flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-muted">
          <ArrowLeft aria-hidden className="size-5" />
        </Link>
        <h1 className="min-w-0 flex-1 truncate font-display text-xl font-bold sm:text-2xl">{templateId ? "Edit template" : "New template"}</h1>
        <button type="button" onClick={() => fileInput.current?.click()} aria-label="Import template" title="Import a template file" className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted">
          <Upload aria-hidden className="size-5" />
        </button>
        <button
          type="button"
          aria-label="Export template"
          title="Export as a file"
          onClick={() => {
            const url = URL.createObjectURL(new Blob([exportJson(draft)], { type: "application/json" }));
            const a = document.createElement("a");
            a.href = url;
            a.download = `${draft.name.trim() || "template"}.json`;
            a.click();
            URL.revokeObjectURL(url);
          }}
          className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted"
        >
          <Download aria-hidden className="size-5" />
        </button>
        <button type="button" disabled={save.isPending} onClick={submit} className={buttonPrimary}>
          {save.isPending && <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" />}
          Save
        </button>
        <input
          ref={fileInput}
          type="file"
          accept="application/json,.json"
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (!file) return;
            void file.text().then((text) => {
              try {
                update(importJson(text));
                toast("Template imported. Review it, then save.");
              } catch (err) {
                toast.error(err instanceof Error ? err.message : "This file could not be imported.");
              }
            });
          }}
        />
      </header>

      {restore && (
        <div role="status" className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted p-3 text-sm">
          <span className="flex-1">You have unsaved changes from earlier on this device.</span>
          <button type="button" onClick={() => { setDraft(restore); setDirty(true); setRestore(null); }} className={buttonSecondary}>Restore</button>
          <button type="button" onClick={() => { writeDraft(draftKey, null); setRestore(null); }} className={buttonSecondary}>Discard</button>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
        <div className="flex min-w-0 flex-col gap-4">
          <div className="flex flex-col gap-2">
            <label htmlFor={nameId} className="text-sm font-medium">Name</label>
            <input
              id={nameId}
              value={draft.name}
              maxLength={80}
              placeholder="For example: Methods review"
              aria-invalid={showProblems && problems.name ? true : undefined}
              aria-describedby={showProblems && problems.name ? `${nameId}-error` : undefined}
              onChange={(e) => { update({ ...draft, name: e.target.value }); }}
              className={inputClass}
            />
            <FieldError id={`${nameId}-error`} message={showProblems ? problems.name : undefined} />
            <label htmlFor={`${nameId}-d`} className="sr-only">Description</label>
            <input
              id={`${nameId}-d`}
              value={draft.description}
              maxLength={300}
              placeholder="What this template is for (optional)"
              onChange={(e) => { update({ ...draft, description: e.target.value }); }}
              className={inputClass}
            />
          </div>

          <div className="flex items-center gap-2">
            <h2 className="font-display text-lg font-bold">Fields</h2>
            <span className="text-sm text-text-secondary tabular-nums">{`${String(draft.fields.length)}/${String(max)}`}</span>
          </div>
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={(event: DragEndEvent) => {
              const { active, over } = event;
              if (!over || active.id === over.id) return;
              const from = draft.fields.findIndex((f) => f.id === active.id);
              const to = draft.fields.findIndex((f) => f.id === over.id);
              update({ ...draft, fields: arrayMove(draft.fields, from, to) });
            }}
          >
            <SortableContext items={draft.fields.map((f) => f.id)} strategy={verticalListSortingStrategy}>
              <ol aria-label="Fields" className="flex flex-col gap-3">
                {draft.fields.map((field, index) => (
                  <FieldCard
                    key={field.id}
                    field={field}
                    index={index}
                    count={draft.fields.length}
                    limits={limitValues}
                    problem={showProblems ? problems.fields[field.id] : undefined}
                    canAdd={!atLimit}
                    onChange={(next) => { update({ ...draft, fields: draft.fields.map((f) => (f.id === next.id ? next : f)) }); }}
                    onMove={(from, to) => { update({ ...draft, fields: arrayMove(draft.fields, from, to) }); }}
                    onDuplicate={() => {
                      const copy = { ...field, id: crypto.randomUUID(), key: null, label: `${field.label} (copy)`.slice(0, 60) };
                      const fields = [...draft.fields];
                      fields.splice(index + 1, 0, copy);
                      update({ ...draft, fields });
                    }}
                    onRemove={() => { update({ ...draft, fields: draft.fields.filter((f) => f.id !== field.id) }); }}
                  />
                ))}
              </ol>
            </SortableContext>
          </DndContext>
          {showProblems && problems.form && <FieldError id="template-form-error" message={problems.form} />}
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" disabled={atLimit} onClick={() => { update({ ...draft, fields: [...draft.fields, newField()] }); }} className={buttonSecondary}>
              <Plus aria-hidden className="size-4" />
              Add field
            </button>
            {atLimit && <span className="text-sm text-text-secondary">{`Templates can have up to ${String(max)} fields.`}</span>}
          </div>
        </div>

        <aside aria-labelledby="preview-heading" className="flex min-w-0 flex-col gap-3 rounded-lg border border-border bg-surface p-4 lg:sticky lg:top-4 lg:self-start">
          <h2 id="preview-heading" className="font-display text-lg font-bold">Try on a paper</h2>
          {papers.data && papers.data.length > 0 ? (
            <div className="flex min-w-0 items-center gap-2">
              <Select
                className="flex-1"
                label="Paper"
                value={paperId || papers.data[0]?.id || ""}
                options={papers.data.map((p) => ({ value: p.id, label: p.title ?? p.filename }))}
                onChange={setPaperId}
                align="left"
                width="w-72"
              />
              <button type="button" disabled={previewing} onClick={() => void runPreview()} className={`${buttonSecondary} shrink-0`}>
                {previewing ? <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> : <Play aria-hidden className="size-4" />}
                {previewing ? "Running" : "Run"}
              </button>
            </div>
          ) : (
            <p className="text-sm text-text-secondary">Upload a paper to try this template on it.</p>
          )}
          <p className="text-xs text-text-secondary">Runs the template once on the paper. Nothing is saved.</p>
          {preview && (
            <ol aria-label="Preview" aria-live="polite" className="flex flex-col gap-3">
              {preview.map((f) => (
                <li key={f.key} className="flex flex-col gap-1 border-t border-border pt-3 first:border-0 first:pt-0">
                  <p className="text-sm font-medium">{labelsByKey.get(f.key) ?? f.key}</p>
                  <p className="text-sm whitespace-pre-line">{f.value}</p>
                  {f.status === "not_reported" && <p className="text-xs text-text-secondary">Not reported in this paper</p>}
                </li>
              ))}
              {previewing && <li className="text-sm text-text-secondary">Writing the next field</li>}
            </ol>
          )}
        </aside>
      </div>

      {stale !== null && (
        <Dialog
          open
          title="Changed in another tab"
          onClose={() => { setStale(null); }}
          footer={
            <>
              <button
                type="button"
                onClick={() => {
                  setStale(null);
                  void getTemplate(templateId ?? "").then((fresh) => {
                    writeDraft(draftKey, null);
                    setDraft(fromTemplate(fresh));
                    setBaseVersion(fresh.version);
                    setDirty(false);
                  });
                }}
                className={buttonSecondary}
              >
                Load the newer version
              </button>
              <button type="button" onClick={() => { const v = stale; setStale(null); save.mutate(v); }} className={buttonPrimary}>
                Save mine anyway
              </button>
            </>
          }
        >
          <p>{`This template was saved as version ${String(stale)} somewhere else. Load that version, or save your changes on top of it.`}</p>
        </Dialog>
      )}

      {blocker.status === "blocked" && (
        <Dialog
          open
          title="Leave without saving?"
          onClose={blocker.reset}
          footer={
            <>
              <button type="button" onClick={blocker.reset} className={buttonSecondary}>Keep editing</button>
              <button type="button" onClick={blocker.proceed} className={buttonPrimary}>Leave</button>
            </>
          }
        >
          <p>Your changes are kept as a draft on this device, and you can restore them when you come back.</p>
        </Dialog>
      )}
    </div>
  );
}
