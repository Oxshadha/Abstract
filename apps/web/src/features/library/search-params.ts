import type { DocType, LibraryParams, Sort } from "./api";

const SORTS: readonly Sort[] = ["added", "opened", "title"];
const TYPES: readonly DocType[] = ["paper", "report", "article"];
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** What the Library URL may carry; every field is optional so plain links stay valid. */
export type LibrarySearch = Partial<LibraryParams>;

/** Library URL state (spec 013 AC3): unknown or malformed values are dropped. */
export function parseLibrarySearch(search: Record<string, unknown>): LibrarySearch {
  const sort = SORTS.find((s) => s === search.sort);
  const type = TYPES.find((t) => t === search.type);
  const collection = typeof search.collection === "string" && UUID.test(search.collection) ? search.collection : undefined;
  const starred = search.starred === true || search.starred === "true";
  const trash = search.trash === true || search.trash === "true";
  return {
    ...(sort && sort !== "added" ? { sort } : {}),
    ...(type ? { type } : {}),
    ...(starred ? { starred: true } : {}),
    ...(collection ? { collection } : {}),
    ...(trash ? { trash: true } : {}),
  };
}

export function withDefaults(search: LibrarySearch): LibraryParams {
  return { ...search, sort: search.sort ?? "added" };
}
