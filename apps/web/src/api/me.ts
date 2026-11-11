import { api } from "./client";
import type { components } from "./schema";

export type Me = components["schemas"]["Me"];

export async function fetchMe(): Promise<Me> {
  const { data, response } = await api.GET("/api/v1/me");
  if (!response.ok || !data) throw new Error("Could not load your profile");
  return data;
}
