import { useQuery } from "@tanstack/react-query";
import { Check, FolderInput, FolderMinus, FolderPlus, Pencil, Plus, Star, Trash2 } from "lucide-react";
import { useState, type SubmitEvent } from "react";

import { Dialog, buttonPrimary, buttonSecondary, inputClass } from "@/components/dialog/Dialog";
import { Menu } from "@/components/menu/Menu";
import { toast } from "@/components/status/toast";
import type { Paper } from "@/features/papers/api";

import { libraryKeys, listCollections, paperCollections } from "./api";
import { paperName } from "./format";
import { useCollectionActions, useDeletePaper, useMembership, useMove, useUpdatePaper } from "./mutations";
import { useOpenCollection } from "./useOpenCollection";

/** Star toggle shown on every row and in the Workspace header (AC5). */
export function StarButton({ paper }: { paper: Paper }) {
  const update = useUpdatePaper();
  const name = paperName(paper);
  return (
    <button
      type="button"
      aria-pressed={paper.starred}
      aria-label={paper.starred ? `Unstar ${name}` : `Star ${name}`}
      title={paper.starred ? "Unstar" : "Star"}
      onClick={() => { update.mutate({ id: paper.id, change: { starred: !paper.starred } }); }}
      className="inline-flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-muted"
    >
      <Star aria-hidden className={`size-5 ${paper.starred ? "fill-current" : ""}`} />
    </button>
  );
}

type Open = "collections" | "move" | "rename" | "delete" | null;

/** The "..." menu on a Library row or card (AC2, AC5, AC7). */
export function PaperMenu({ paper }: { paper: Paper }) {
  const [open, setOpen] = useState<Open>(null);
  const update = useUpdatePaper();
  const inCollection = useOpenCollection();
  const toggle = useMembership(paper.id);
  const name = paperName(paper);
  const close = () => { setOpen(null); };
  // Inside a collection the paper can also be moved out or removed (like moving a chat between
  // projects); a paper may still live in several collections at once.
  const collectionItems = inCollection
    ? [
        { label: "Move to collection", icon: <FolderInput aria-hidden className="size-4" />, onSelect: () => { setOpen("move"); } },
        {
          label: "Remove from this collection",
          icon: <FolderMinus aria-hidden className="size-4" />,
          onSelect: () => { toggle.mutate({ collectionId: inCollection, member: false }); },
        },
      ]
    : [];
  return (
    <>
      <Menu
        label={`Actions for ${name}`}
        items={[
          {
            label: paper.starred ? "Unstar" : "Star",
            icon: <Star aria-hidden className="size-4" />,
            onSelect: () => { update.mutate({ id: paper.id, change: { starred: !paper.starred } }); },
          },
          { label: "Add to collection", icon: <FolderPlus aria-hidden className="size-4" />, onSelect: () => { setOpen("collections"); } },
          ...collectionItems,
          { label: "Rename", icon: <Pencil aria-hidden className="size-4" />, onSelect: () => { setOpen("rename"); } },
          { label: "Delete", icon: <Trash2 aria-hidden className="size-4" />, destructive: true, onSelect: () => { setOpen("delete"); } },
        ]}
      />
      {open === "collections" && <CollectionsDialog paper={paper} onClose={close} />}
      {open === "move" && inCollection && <MoveDialog paper={paper} from={inCollection} onClose={close} />}
      {open === "rename" && <RenameDialog paper={paper} onClose={close} />}
      {open === "delete" && <DeleteDialog paper={paper} onClose={close} />}
    </>
  );
}

function CollectionsDialog({ paper, onClose }: { paper: Paper; onClose: () => void }) {
  const collections = useQuery({ queryKey: libraryKeys.collections, queryFn: listCollections });
  const membership = useQuery({ queryKey: libraryKeys.paperCollections(paper.id), queryFn: () => paperCollections(paper.id) });
  const toggle = useMembership(paper.id);
  const { create } = useCollectionActions();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const member = new Set(membership.data ?? []);

  const onCreate = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    create.mutate(trimmed, {
      onSuccess: (created) => {
        setName("");
        setError(null);
        toggle.mutate({ collectionId: created.id, member: true });
      },
      onError: (err) => { setError(err.message); },
    });
  };

  return (
    <Dialog open title="Add to collection" onClose={onClose} footer={<button type="button" onClick={onClose} className={buttonPrimary}>Done</button>}>
      <p className="text-sm text-text-secondary">{paperName(paper)}</p>
      {collections.isPending ? (
        <p className="text-sm text-text-secondary">Loading collections</p>
      ) : (collections.data ?? []).length === 0 ? (
        <p className="text-sm text-text-secondary">No collections yet. Create your first one below.</p>
      ) : (
        <ul className="flex max-h-64 flex-col gap-1 overflow-auto" aria-label="Collections">
          {(collections.data ?? []).map((c) => {
            const checked = member.has(c.id);
            return (
              <li key={c.id}>
                <button
                  type="button"
                  role="checkbox"
                  aria-checked={checked}
                  onClick={() => { toggle.mutate({ collectionId: c.id, member: !checked }); }}
                  className="flex min-h-11 w-full items-center gap-3 rounded-md px-2 text-left hover:bg-muted"
                >
                  <span aria-hidden className={`flex size-5 items-center justify-center rounded-sm border ${checked ? "border-primary bg-primary text-primary-text" : "border-border-strong"}`}>
                    {checked && <Check className="size-4" />}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{c.name}</span>
                  <span className="text-sm text-text-secondary">{c.paper_count}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <form onSubmit={onCreate} className="flex gap-2">
        <label className="sr-only" htmlFor={`new-collection-${paper.id}`}>New collection name</label>
        <input
          id={`new-collection-${paper.id}`}
          value={name}
          maxLength={60}
          placeholder="New collection"
          onChange={(e) => { setName(e.target.value); }}
          aria-invalid={error ? true : undefined}
          className={inputClass}
        />
        <button type="submit" disabled={!name.trim() || create.isPending} className={buttonSecondary}>
          <Plus aria-hidden className="size-4" />
          Create
        </button>
      </form>
      {error && <p role="alert" className="text-sm text-error">{error}</p>}
    </Dialog>
  );
}

/** Move from the open collection to another one (D84): added there, removed here. */
function MoveDialog({ paper, from, onClose }: { paper: Paper; from: string; onClose: () => void }) {
  const collections = useQuery({ queryKey: libraryKeys.collections, queryFn: listCollections });
  const move = useMove(paper.id);
  const targets = (collections.data ?? []).filter((c) => c.id !== from);
  return (
    <Dialog open title="Move to collection" onClose={onClose}>
      <p className="text-sm text-text-secondary">{paperName(paper)}</p>
      {collections.isSuccess && targets.length === 0 ? (
        <p className="text-sm text-text-secondary">Create another collection first, then move papers into it.</p>
      ) : (
        <ul className="flex max-h-64 flex-col gap-1 overflow-auto" aria-label="Move to">
          {targets.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                disabled={move.isPending}
                onClick={() => { move.mutate({ from, to: c.id }, { onSuccess: onClose }); }}
                className="flex min-h-11 w-full items-center gap-3 rounded-md px-2 text-left hover:bg-muted disabled:opacity-50"
              >
                <FolderInput aria-hidden className="size-4 shrink-0" />
                <span className="min-w-0 flex-1 truncate">{c.name}</span>
                <span className="text-sm text-text-secondary">{c.paper_count}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}

function RenameDialog({ paper, onClose }: { paper: Paper; onClose: () => void }) {
  const update = useUpdatePaper();
  const [title, setTitle] = useState(paperName(paper));
  const submit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    update.mutate({ id: paper.id, change: { title: trimmed } });
    onClose();
  };
  return (
    <Dialog open title="Rename paper" onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          Title
          <input value={title} maxLength={300} onChange={(e) => { setTitle(e.target.value); }} className={inputClass} />
        </label>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className={buttonSecondary}>Cancel</button>
          <button type="submit" disabled={!title.trim()} className={buttonPrimary}>Save</button>
        </div>
      </form>
    </Dialog>
  );
}

function DeleteDialog({ paper, onClose }: { paper: Paper; onClose: () => void }) {
  const remove = useDeletePaper();
  return (
    <Dialog
      open
      title="Delete paper?"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} className={buttonSecondary}>Cancel</button>
          <button
            type="button"
            disabled={remove.isPending}
            onClick={() => {
              remove.mutate(paper.id, { onSuccess: onClose, onError: () => { toast.error("Could not delete the paper."); } });
            }}
            className={buttonPrimary}
          >
            Delete
          </button>
        </>
      }
    >
      <p>
        <span className="font-medium">{paperName(paper)}</span> and its summaries, chats and notes will be deleted. This cannot be undone.
      </p>
    </Dialog>
  );
}
