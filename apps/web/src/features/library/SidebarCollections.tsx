import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { Folder, Pencil, Plus, Trash2 } from "lucide-react";
import { useState, type SubmitEvent } from "react";

import { Dialog, buttonPrimary, buttonSecondary, inputClass } from "@/components/dialog/Dialog";
import { Menu } from "@/components/menu/Menu";
import { FieldError } from "@/components/status/FieldError";

import { libraryKeys, listCollections, type Collection } from "./api";
import { useCollectionActions } from "./mutations";
import { useOpenCollection } from "./useOpenCollection";

/** Collections as sidebar folders over the Library (spec 013 AC6, AC7; D82). */
export function SidebarCollections({ onNavigate }: { onNavigate?: () => void }) {
  const collections = useQuery({ queryKey: libraryKeys.collections, queryFn: listCollections, staleTime: 60_000 });
  const openCollection = useOpenCollection();
  const [dialog, setDialog] = useState<{ mode: "create" } | { mode: "rename" | "delete"; collection: Collection } | null>(null);

  return (
    <section aria-labelledby="collections-heading" className="flex min-h-0 flex-col gap-1 border-t border-border pt-4">
      <div className="flex items-center px-3">
        <h2 id="collections-heading" className="text-xs font-medium tracking-wide text-text-secondary uppercase">
          Collections
        </h2>
        <button
          type="button"
          aria-label="New collection"
          title="New collection"
          onClick={() => { setDialog({ mode: "create" }); }}
          className="ml-auto inline-flex size-11 items-center justify-center rounded-md text-text-secondary hover:bg-muted hover:text-text"
        >
          <Plus aria-hidden className="size-4" />
        </button>
      </div>
      {collections.isSuccess && collections.data.length === 0 && (
        <p className="px-3 text-sm text-text-secondary">Group related papers into collections.</p>
      )}
      <ul className="flex min-h-0 flex-col gap-0.5 overflow-auto">
        {(collections.data ?? []).map((c) => {
          const active = openCollection === c.id;
          return (
            <li key={c.id} className={`group flex items-center rounded-md ${active ? "bg-muted" : "hover:bg-muted"}`}>
              <Link
                to="/app/library"
                search={{ collection: c.id }}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-11 min-w-0 flex-1 items-center gap-3 px-3 ${active ? "font-medium text-text" : "text-text-secondary hover:text-text"}`}
              >
                <Folder aria-hidden className="size-5 shrink-0" />
                <span className="min-w-0 flex-1 truncate">{c.name}</span>
                <span className="text-sm tabular-nums">{c.paper_count}</span>
              </Link>
              <Menu
                label={`Actions for collection ${c.name}`}
                items={[
                  { label: "Rename", icon: <Pencil aria-hidden className="size-4" />, onSelect: () => { setDialog({ mode: "rename", collection: c }); } },
                  { label: "Delete", icon: <Trash2 aria-hidden className="size-4" />, destructive: true, onSelect: () => { setDialog({ mode: "delete", collection: c }); } },
                ]}
              />
            </li>
          );
        })}
      </ul>
      {dialog?.mode === "create" && <NameDialog title="New collection" onClose={() => { setDialog(null); }} />}
      {dialog?.mode === "rename" && <NameDialog title="Rename collection" collection={dialog.collection} onClose={() => { setDialog(null); }} />}
      {dialog?.mode === "delete" && <DeleteCollection collection={dialog.collection} onClose={() => { setDialog(null); }} />}
    </section>
  );
}

/**
 * Phones (D86): collections as a scrollable chip row at the top of the Library, since there is
 * no sidebar. The open collection gets a "..." for Rename and Delete; "+" creates one.
 */
export function CollectionChips() {
  const collections = useQuery({ queryKey: libraryKeys.collections, queryFn: listCollections, staleTime: 60_000 });
  const openCollection = useOpenCollection();
  const [dialog, setDialog] = useState<{ mode: "create" } | { mode: "rename" | "delete"; collection: Collection } | null>(null);
  const active = collections.data?.find((c) => c.id === openCollection);
  const chip = (on: boolean) =>
    `inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-pill border px-3 text-sm whitespace-nowrap ${on ? "border-primary bg-primary text-primary-text" : "border-border text-text-secondary"}`;
  return (
    <div className="-mx-4 flex items-center gap-2 overflow-x-auto px-4 md:hidden" role="group" aria-label="Collections">
      <Link to="/app/library" aria-current={!openCollection ? "page" : undefined} className={chip(!openCollection)}>
        All papers
      </Link>
      {(collections.data ?? []).map((c) => (
        <Link key={c.id} to="/app/library" search={{ collection: c.id }} aria-current={c.id === openCollection ? "page" : undefined} className={chip(c.id === openCollection)}>
          <Folder aria-hidden className="size-4" />
          {c.name}
          <span className="tabular-nums opacity-70">{c.paper_count}</span>
        </Link>
      ))}
      <button type="button" aria-label="New collection" title="New collection" onClick={() => { setDialog({ mode: "create" }); }} className="inline-flex size-9 shrink-0 items-center justify-center rounded-pill border border-border text-text-secondary">
        <Plus aria-hidden className="size-4" />
      </button>
      {active && (
        <Menu
          label={`Actions for collection ${active.name}`}
          items={[
            { label: "Rename", icon: <Pencil aria-hidden className="size-4" />, onSelect: () => { setDialog({ mode: "rename", collection: active }); } },
            { label: "Delete", icon: <Trash2 aria-hidden className="size-4" />, destructive: true, onSelect: () => { setDialog({ mode: "delete", collection: active }); } },
          ]}
        />
      )}
      {dialog?.mode === "create" && <NameDialog title="New collection" onClose={() => { setDialog(null); }} />}
      {dialog?.mode === "rename" && <NameDialog title="Rename collection" collection={dialog.collection} onClose={() => { setDialog(null); }} />}
      {dialog?.mode === "delete" && <DeleteCollection collection={dialog.collection} onClose={() => { setDialog(null); }} />}
    </div>
  );
}

function NameDialog({ title, collection, onClose }: { title: string; collection?: Collection; onClose: () => void }) {
  const { create, rename } = useCollectionActions();
  const navigate = useNavigate();
  const [name, setName] = useState(collection?.name ?? "");
  const [error, setError] = useState<string | null>(null);
  const pending = create.isPending || rename.isPending;
  const submit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    const fail = (err: Error) => { setError(err.message); };
    if (collection) {
      rename.mutate({ id: collection.id, name: trimmed }, { onSuccess: onClose, onError: fail });
    } else {
      create.mutate(trimmed, {
        onSuccess: (created) => {
          onClose();
          void navigate({ to: "/app/library", search: { collection: created.id } });
        },
        onError: fail,
      });
    }
  };
  return (
    <Dialog open title={title} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          Name
          <input
            value={name}
            maxLength={60}
            onChange={(e) => { setName(e.target.value); setError(null); }}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? "collection-name-error" : undefined}
            className={inputClass}
          />
        </label>
        <FieldError id="collection-name-error" message={error} />
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className={buttonSecondary}>Cancel</button>
          <button type="submit" disabled={!name.trim() || pending} className={buttonPrimary}>{collection ? "Save" : "Create"}</button>
        </div>
      </form>
    </Dialog>
  );
}

function DeleteCollection({ collection, onClose }: { collection: Collection; onClose: () => void }) {
  const { remove } = useCollectionActions();
  const navigate = useNavigate();
  const openCollection = useOpenCollection();
  return (
    <Dialog
      open
      title="Delete collection?"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} className={buttonSecondary}>Cancel</button>
          <button
            type="button"
            disabled={remove.isPending}
            onClick={() => {
              remove.mutate(collection.id, {
                onSuccess: () => {
                  onClose();
                  if (openCollection === collection.id) void navigate({ to: "/app/library" });
                },
              });
            }}
            className={buttonPrimary}
          >
            Delete
          </button>
        </>
      }
    >
      <p>
        <span className="font-medium">{collection.name}</span> will be deleted. Its {collection.paper_count === 1 ? "paper stays" : "papers stay"} in your Library.
      </p>
    </Dialog>
  );
}
