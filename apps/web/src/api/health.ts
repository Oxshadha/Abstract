import { api } from "./client";

export type HealthStatus = "ok" | "down";

/** Never throws: network failures and error responses both map to "down". */
export async function fetchHealth(): Promise<HealthStatus> {
  try {
    const { data, response } = await api.GET("/api/v1/healthz");
    return response.ok && data?.status === "ok" ? "ok" : "down";
  } catch {
    return "down";
  }
}
