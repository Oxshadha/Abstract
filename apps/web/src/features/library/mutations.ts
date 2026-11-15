import { useMutation, useQueryClient, type InfiniteData, type QueryClient } from "@tanstack/react-query";

import { toast } from "@/components/status/toast";
import { deletePaper, paperKeys, type Paper, type PaperPage } from "@/features/papers/api";

import { useFlag } from "@/features/flags/api";

import {
  createCollection,
  deleteCollection,
  deleteForever,
  emptyTrash,
  libraryKeys,
  renameCollection,
  restorePaper,
  setMembership,
  updatePaper,
  type Collection,
} from "./api";

type Cached = InfiniteData<PaperPage> | PaperPage | undefined;

function edit(data: Cached, paperId: string, change: Partial<Paper>): Cached {
  if (!data) return data;
  const page = (p: PaperPage): PaperPage => ({ ...p, items: p.items.map((i) => (i.id === paperId ? { ...i, ...change } : i)) });
  return "pages" in data ? { ...data, pages: data.pages.map(page) } : page(data);
}

/** Apply `change` to the paper in every cached list (Library pages, Home) and its detail. */
function patchPaper(client: QueryClient, paperId: string, change: Partial<Paper>) {
  const lists = client.getQueriesData<Cached>({ queryKey: ["papers", "list"] });
  const detail = client.getQueryData<Paper>(paperKeys.detail(paperId));
  for (const [key, data] of lists) client.setQueryData<Cached>(key, edit(data, paperId, change));
  if (detail) client.setQueryData(paperKeys.detail(paperId), { ...detail, ...change });
  return () => {
    for (const [key, data] of lists) client.setQueryData(key, data);
    if (detail) client.setQueryData(paperKeys.detail(paperId), detail);
  };
}

/** Star and rename (AC5, AC12): instant, rolled back with a toast if the server refuses. */
export function useUpdatePaper() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, change }: { id: string; change: { title?: string; starred?: boolean } }) => updatePaper(id, change),
    onMutate: async ({ id, change }) => {
      await client.cancelQueries({ queryKey: ["papers"] });
      return { undo: patchPaper(client, id, change) };
    },
    onError: (err, _vars, context) => {
      context?.undo();
      toast.error(err.message);
    },
    onSettled: (_data, _err, { change }) => {
      // A star changes the Starred filter; a rename can change the title sort order.
      void client.invalidateQueries({ queryKey: ["papers", "list"], refetchType: change.title ? "active" : "none" });
    },
  });
}

function refreshPapers(client: QueryClient) {
  void client.invalidateQueries({ queryKey: ["papers"] });
  void client.invalidateQueries({ queryKey: libraryKeys.collections });
}

/** Restore from Recently deleted (spec 019 AC4), also the toast's Undo (AC2). */
export function useRestorePaper() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => restorePaper(id),
    onSuccess: () => {
      toast("Paper restored.");
      refreshPapers(client);
    },
    onError: (err) => toast.error(err.message),
  });
}

/** Delete moves the paper to Recently deleted while that is on (spec 019 AC1, AC2). */
export function useDeletePaper() {
  const client = useQueryClient();
  const bin = useFlag("recently_deleted");
  const restore = useRestorePaper();
  return useMutation({
    mutationFn: (id: string) => deletePaper(id),
    onSuccess: (_data, id) => {
      if (bin) toast("Moved to Recently deleted.", { duration: 8000, action: { label: "Undo", onClick: () => { restore.mutate(id); } } });
      else toast("Paper deleted.");
      refreshPapers(client);
    },
    onError: (err) => toast.error(err.message),
  });
}

/** Delete forever and Empty (spec 019 AC5). */
export function useDeleteForever() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteForever(id),
    onSuccess: () => {
      toast("Paper deleted for good.");
      refreshPapers(client);
    },
    onError: (err) => toast.error(err.message),
  });
}

export function useEmptyTrash() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: emptyTrash,
    onSuccess: (count) => {
      toast(count === 1 ? "1 paper deleted for good." : `${String(count)} papers deleted for good.`);
      refreshPapers(client);
    },
    onError: (err) => toast.error(err.message),
  });
}

/** Add to or remove from a collection (AC7, AC12), optimistic on the menu and the counts. */
export function useMembership(paperId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ collectionId, member }: { collectionId: string; member: boolean }) => setMembership(collectionId, paperId, member),
    onMutate: async ({ collectionId, member }) => {
      const key = libraryKeys.paperCollections(paperId);
      await client.cancelQueries({ queryKey: key });
      const before = client.getQueryData<string[]>(key);
      const counts = client.getQueryData<Collection[]>(libraryKeys.collections);
      client.setQueryData<string[]>(key, (ids = []) => (member ? [...new Set([...ids, collectionId])] : ids.filter((c) => c !== collectionId)));
      client.setQueryData<Collection[]>(libraryKeys.collections, (list) =>
        list?.map((c) => (c.id === collectionId ? { ...c, paper_count: Math.max(0, c.paper_count + (member ? 1 : -1)) } : c)),
      );
      return { before, counts };
    },
    onError: (err, _vars, context) => {
      client.setQueryData(libraryKeys.paperCollections(paperId), context?.before);
      client.setQueryData(libraryKeys.collections, context?.counts);
      toast.error(err.message);
    },
    onSettled: (_d, _e, { collectionId }) => {
      void client.invalidateQueries({ queryKey: libraryKeys.collections });
      void client.invalidateQueries({ queryKey: ["papers", "list", { collection: collectionId }], exact: false });
    },
  });
}

/** Move a paper between collections (D84): add to the target first, then remove from the source. */
export function useMove(paperId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ from, to }: { from: string; to: string }) => {
      await setMembership(to, paperId, true);
      await setMembership(from, paperId, false);
    },
    onSuccess: () => { toast("Paper moved."); },
    onError: (err) => toast.error(err.message),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: libraryKeys.collections });
      void client.invalidateQueries({ queryKey: libraryKeys.paperCollections(paperId) });
      void client.invalidateQueries({ queryKey: ["papers", "list"] });
    },
  });
}

export function useCollectionActions() {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: libraryKeys.collections });
  return {
    create: useMutation({
      mutationFn: (name: string) => createCollection(name),
      onSuccess: (created) => {
        client.setQueryData<Collection[]>(libraryKeys.collections, (list = []) =>
          [...list, created].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" })),
        );
        void refresh();
      },
    }),
    rename: useMutation({
      mutationFn: ({ id, name }: { id: string; name: string }) => renameCollection(id, name),
      onMutate: ({ id, name }) => {
        const before = client.getQueryData<Collection[]>(libraryKeys.collections);
        client.setQueryData<Collection[]>(libraryKeys.collections, (list) => list?.map((c) => (c.id === id ? { ...c, name } : c)));
        return { before };
      },
      onError: (err, _vars, context) => {
        client.setQueryData(libraryKeys.collections, context?.before);
        toast.error(err.message);
      },
      onSettled: () => void refresh(),
    }),
    remove: useMutation({
      mutationFn: (id: string) => deleteCollection(id),
      onSuccess: () => {
        toast("Collection deleted. Its papers are still in your Library.");
        void refresh();
      },
      onError: (err) => toast.error(err.message),
    }),
  };
}
