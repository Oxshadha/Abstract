import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { Copy, LayoutGrid, Lock, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { Dialog, buttonPrimary, buttonSecondary } from "@/components/dialog/Dialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ListRowSkeleton, Loading } from "@/components/feedback/Skeleton";
import { Menu } from "@/components/menu/Menu";
import { toast } from "@/components/status/toast";
import { timeAgo } from "@/features/papers/format";
import { listTemplates } from "@/features/summaries/api";

import { deleteTemplate, duplicateTemplate, templateKeys, type Template } from "./api";

function fieldCount(t: Template): string {
  return `${String(t.fields.length)} ${t.fields.length === 1 ? "field" : "fields"}`;
}

/** Templates (spec 010 AC1, AC2): system templates to duplicate, the user's own to edit. */
export function TemplatesPage() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const templates = useQuery({ queryKey: templateKeys.list, queryFn: listTemplates });
  const [deleting, setDeleting] = useState<Template | null>(null);
  const duplicate = useMutation({
    mutationFn: (id: string) => duplicateTemplate(id),
    onSuccess: (copy) => {
      void client.invalidateQueries({ queryKey: templateKeys.list });
      void navigate({ to: "/app/templates/$templateId", params: { templateId: copy.id } });
    },
    onError: (err) => toast.error(err.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteTemplate(id),
    onSuccess: () => {
      toast("Template deleted. Summaries made with it keep working.");
      setDeleting(null);
      void client.invalidateQueries({ queryKey: templateKeys.list });
    },
    onError: (err) => toast.error(err.message),
  });

  const system = templates.data?.filter((t) => t.kind === "system") ?? [];
  const mine = templates.data?.filter((t) => t.kind === "custom") ?? [];

  return (
    <div className="flex flex-col gap-6 px-4 pt-4 pb-10 sm:pt-6 md:px-8">
      <header className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Templates</h1>
          <p className="mt-1 hidden text-text-secondary sm:block">Choose what a summary extracts. Build your own like a form.</p>
        </div>
        <Link to="/app/templates/new" className={buttonPrimary}>
          <Plus aria-hidden className="size-5" />
          <span className="hidden sm:inline">New template</span>
          <span className="sm:hidden">New</span>
        </Link>
      </header>

      {templates.isPending ? (
        <Loading label="Loading templates">
          <ListRowSkeleton />
          <ListRowSkeleton />
        </Loading>
      ) : templates.isError ? (
        <div role="alert" className="rounded-lg border border-border p-4">{templates.error.message}</div>
      ) : (
        <>
          <section aria-labelledby="yours-heading" className="flex flex-col gap-3">
            <h2 id="yours-heading" className="font-display text-lg font-bold sm:text-xl">Your templates</h2>
            {mine.length === 0 ? (
              <EmptyState
                icon={LayoutGrid}
                title="No templates of your own yet"
                description="Make one from scratch, or duplicate a system template and change its fields."
              />
            ) : (
              <ul aria-label="Your templates" className="flex flex-col gap-3">
                {mine.map((t) => (
                  <li key={t.id} className="relative flex items-center gap-3 rounded-lg border border-border bg-surface py-2 pr-1 pl-3 sm:p-4">
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted">
                      <LayoutGrid aria-hidden className="size-5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <Link
                        to="/app/templates/$templateId"
                        params={{ templateId: t.id }}
                        className="block truncate font-medium after:absolute after:inset-0 after:rounded-lg hover:underline"
                      >
                        {t.name}
                      </Link>
                      <p className="truncate text-sm text-text-secondary">
                        {fieldCount(t)}
                        {t.updated_at ? ` · updated ${timeAgo(t.updated_at)}` : ""}
                      </p>
                    </div>
                    <span className="relative z-10 flex shrink-0 items-center">
                      <Link to="/app/templates/$templateId" params={{ templateId: t.id }} aria-label={`Edit ${t.name}`} title="Edit" className="inline-flex size-11 items-center justify-center rounded-md hover:bg-muted">
                        <Pencil aria-hidden className="size-5" />
                      </Link>
                      <Menu
                        label={`Actions for ${t.name}`}
                        items={[
                          { label: "Duplicate", icon: <Copy aria-hidden className="size-4" />, onSelect: () => { duplicate.mutate(t.id); } },
                          { label: "Delete", icon: <Trash2 aria-hidden className="size-4" />, destructive: true, onSelect: () => { setDeleting(t); } },
                        ]}
                      />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="system-heading" className="flex flex-col gap-3">
            <h2 id="system-heading" className="font-display text-lg font-bold sm:text-xl">System templates</h2>
            <ul aria-label="System templates" className="flex flex-col gap-3">
              {system.map((t) => (
                <li key={t.id} className="flex items-center gap-3 rounded-lg border border-border bg-surface py-2 pr-1 pl-3 sm:p-4">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted">
                    <Lock aria-hidden className="size-5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{t.name}</p>
                    <p className="truncate text-sm text-text-secondary">{`${fieldCount(t)} · ${t.description}`}</p>
                  </div>
                  <button
                    type="button"
                    disabled={duplicate.isPending}
                    onClick={() => { duplicate.mutate(t.id); }}
                    aria-label={`Duplicate to customize: ${t.name}`}
                    title="Duplicate to customize"
                    className="inline-flex min-h-11 shrink-0 items-center gap-2 rounded-md border border-border px-3 text-sm hover:bg-muted disabled:opacity-50"
                  >
                    <Copy aria-hidden className="size-4" />
                    <span className="hidden sm:inline">Duplicate to customize</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}

      {deleting && (
        <Dialog
          open
          title="Delete template?"
          onClose={() => { setDeleting(null); }}
          footer={
            <>
              <button type="button" onClick={() => { setDeleting(null); }} className={buttonSecondary}>Cancel</button>
              <button type="button" disabled={remove.isPending} onClick={() => { remove.mutate(deleting.id); }} className={buttonPrimary}>Delete</button>
            </>
          }
        >
          <p>
            <span className="font-medium">{deleting.name}</span> will no longer be offered for new summaries. Summaries already made with it keep working.
          </p>
        </Dialog>
      )}
    </div>
  );
}
