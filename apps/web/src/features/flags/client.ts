import { api } from "@/api/client";
import { problem } from "@/lib/problem";

/** The caller's evaluated feature flags (spec 011 AC6). */
export async function getFlags(): Promise<Record<string, boolean>> {
  const { data, response } = await api.GET("/api/v1/me/flags");
  if (!data) throw await problem(response, "Could not load feature flags.");
  return data.flags;
}
