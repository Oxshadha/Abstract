import { useQuery } from "@tanstack/react-query";
import { FileText, RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";

import { Dialog, buttonPrimary, buttonSecondary } from "@/components/dialog/Dialog";
import { EmptyState } from "@/components/feedback/EmptyState";
import { ListRowSkeleton, Loading } from "@/components/feedback/Skeleton";
import { Menu } from "@/components/menu/Menu";
import { DESTRUCTIVE } from "@/components/status/tone";

import { libraryKeys, listTrash, type TrashedPaper } from "./api";
import { deletesIn } from "./format";
import { useDeleteForever, useEmptyTrash, useRestorePaper } from "./mutations";

function TrashRow({ paper }: { paper: TrashedPaper }) {
  const restore = useRestorePaper();
  const [confirm, setConfirm] = useState(false);
  const remove = useDeleteForever();
  return (
    <li className="flex items-center gap-3 rounded-lg border border-border bg-surface py-2 pr-1 pl-3 sm:gap-4 sm:p-4">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted sm:size-11">
        <FileText aria-hidden className="size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium" title={paper.title}>{paper.title}</p>
        <p className="truncate text-sm text-text-secondary">{deletesIn(paper.purge_at)}</p>
      </div>
      <button
        type="button"
        disabled={restore.isPending}
        onClick={() => { restore.mutate(paper.id); }}
        aria-label={`Restore ${paper.title}`}
        className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center gap-2 rounded-pill border border-border px-3 text-sm hover:bg-muted disabled:opacity-50"
      >
        <RotateCcw aria-hidden className="size-4" />
        <span className="hidden sm:inline">Restore</span>
      </button>
      <Menu
        label={`Actions for ${paper.title}`}
        items={[
          { label: "Delete forever", icon: <Trash2 aria-hidden className="size-4" />, destructive: true, onSelect: () => { setConfirm(true); } },
        ]}
      />
      {confirm && (
        <Dialog
          open
          title="Delete forever?"
          onClose={() => { setConfirm(false); }}
          footer={
            <>
              <button type="button" onClick={() => { setConfirm(false); }} className={buttonSecondary}>Cancel</button>
              <button
                type="button"
                disabled={remove.isPending}
                onClick={() => { remove.mutate(paper.id, { onSuccess: () => { setConfirm(false); } }); }}
                className={buttonPrimary}
              >
                Delete forever
              </button>
            </>
          }
        >
          <p>
            <span className="font-medium">{paper.title}</span> and its summaries, chats and notes are deleted now. They are gone from backups within 7 days. This cannot be undone.
          </p>
        </Dialog>
      )}
    </li>
  );
}

/** Recently deleted in the Library (spec 019 AC3 to AC5). */
export function TrashView() {
  const trash = useQuery({ queryKey: libraryKeys.trash, queryFn: ({ signal }) => listTrash(signal) });
  const empty = useEmptyTrash();
  const [confirm, setConfirm] = useState(false);
  const items = trash.data ?? [];

  if (trash.isPending) {
    return (
      <Loading label="Loading Recently deleted">
        <ListRowSkeleton />
        <ListRowSkeleton />
      </Loading>
    );
  }
  if (trash.isError) {
    return (
      <div role="alert" className="rounded-lg border border-border bg-surface p-4">
        <p>{trash.error.message}</p>
        <button type="button" onClick={() => void trash.refetch()} className="mt-2 min-h-11 underline">Try again</button>
      </div>
    );
  }
  if (items.length === 0) {
    return <EmptyState icon={Trash2} title="Nothing here" description="Deleted papers stay here for 7 days, then they are deleted for good." />;
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <p className="min-w-0 flex-1 text-sm text-text-secondary">Papers stay here for 7 days, then they are deleted for good.</p>
        <button
          type="button"
          onClick={() => { setConfirm(true); }}
          className={`inline-flex min-h-11 shrink-0 items-center gap-2 rounded-pill border border-border px-4 text-sm hover:bg-muted ${DESTRUCTIVE}`}
        >
          <Trash2 aria-hidden className="size-4" />
          Empty
        </button>
      </div>
      <ul aria-label="Recently deleted" className="flex flex-col gap-3">
        {items.map((paper) => <TrashRow key={paper.id} paper={paper} />)}
      </ul>
      {confirm && (
        <Dialog
          open
          title="Empty Recently deleted?"
          onClose={() => { setConfirm(false); }}
          footer={
            <>
              <button type="button" onClick={() => { setConfirm(false); }} className={buttonSecondary}>Cancel</button>
              <button
                type="button"
                disabled={empty.isPending}
                onClick={() => { empty.mutate(undefined, { onSuccess: () => { setConfirm(false); } }); }}
                className={buttonPrimary}
              >
                Delete all forever
              </button>
            </>
          }
        >
          <p>{items.length === 1 ? "1 paper is" : `${String(items.length)} papers are`} deleted now, with their summaries, chats and notes. They are gone from backups within 7 days. This cannot be undone.</p>
        </Dialog>
      )}
    </div>
  );
}
