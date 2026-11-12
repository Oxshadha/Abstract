import { useSearch } from "@tanstack/react-router";

/** The collection open in the Library, from the URL (spec 013 AC7); undefined elsewhere. */
export function useOpenCollection(): string | undefined {
  return useSearch({ strict: false }).collection;
}
