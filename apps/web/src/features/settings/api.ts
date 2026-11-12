import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { problem } from "@/lib/problem";

export type Usage = components["schemas"]["Usage"];
export type Meter = components["schemas"]["Meter"];

export const settingsKeys = { usage: ["me", "usage"] as const };

/** Spec 012 AC12: the plan and what has been used. */
export async function getUsage(): Promise<Usage> {
  const { data, response } = await api.GET("/api/v1/me/usage");
  if (!data) throw await problem(response, "Could not load your usage.");
  return data;
}

/** Spec 012 AC15: disables the account at once; its content is removed in the background. */
export async function deleteAccount(confirmEmail: string): Promise<void> {
  const { response } = await api.DELETE("/api/v1/me", { body: { confirm_email: confirmEmail } });
  if (!response.ok) throw await problem(response, "Could not delete your account.");
}
