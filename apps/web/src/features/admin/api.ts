import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { problem } from "@/lib/problem";

export type Overview = components["schemas"]["Overview"];
export type AdminUser = components["schemas"]["AdminUser"];
export type AdminUserPage = components["schemas"]["AdminUserPage"];
export type Plan = components["schemas"]["PlanOut"];
export type PlanLimits = components["schemas"]["PlanLimitsIn"];
export type Flag = components["schemas"]["FlagOut"];
export type AdminJobs = components["schemas"]["AdminJobs"];
export type AdminJob = components["schemas"]["AdminJob"];
export type ModelEntry = components["schemas"]["RegistryEntryOut"];
export type ModelUpdate = components["schemas"]["RegistryUpdate"];
export type OverviewSeries = components["schemas"]["OverviewSeries"];
export type SeriesRange = OverviewSeries["range"];

export const adminKeys = {
  overview: ["admin", "overview"] as const,
  series: (range: string) => ["admin", "series", range] as const,
  users: (q: string) => ["admin", "users", q] as const,
  plans: ["admin", "plans"] as const,
  flags: ["admin", "flags"] as const,
  jobs: ["admin", "jobs"] as const,
  models: ["admin", "models"] as const,
};

export async function getOverview(): Promise<Overview> {
  const { data, response } = await api.GET("/api/v1/admin/overview");
  if (!data) throw await problem(response, "Could not load the overview.");
  return data;
}

export async function getOverviewSeries(range: SeriesRange): Promise<OverviewSeries> {
  const { data, response } = await api.GET("/api/v1/admin/overview/series", { params: { query: { range } } });
  if (!data) throw await problem(response, "Could not load the charts.");
  return data;
}

export async function setKillSwitch(paidCallsEnabled: boolean): Promise<void> {
  const { response } = await api.PUT("/api/v1/admin/llm/kill-switch", { body: { paid_calls_enabled: paidCallsEnabled } });
  if (!response.ok) throw await problem(response, "Could not change AI calls.");
}

export async function setPlatformCap(dailyUsd: number): Promise<void> {
  const { response } = await api.PUT("/api/v1/admin/llm/cap", { body: { daily_usd: dailyUsd } });
  if (!response.ok) throw await problem(response, "Could not change the daily cap.");
}

export async function listUsers(q: string, cursor: string | null): Promise<AdminUserPage> {
  const { data, response } = await api.GET("/api/v1/admin/users", {
    params: { query: { ...(q ? { q } : {}), ...(cursor ? { cursor } : {}), limit: 25 } },
  });
  if (!data) throw await problem(response, "Could not load users.");
  return data;
}

export async function setUserPlan(userId: string, planId: string): Promise<void> {
  const { response } = await api.PUT("/api/v1/admin/users/{user_id}/plan", { params: { path: { user_id: userId } }, body: { plan_id: planId } });
  if (!response.ok) throw await problem(response, "Could not change the plan.");
}

export async function setUserAdmin(userId: string, admin: boolean): Promise<void> {
  const { response } = admin
    ? await api.POST("/api/v1/admin/users/{user_id}/grant-admin", { params: { path: { user_id: userId } } })
    : await api.POST("/api/v1/admin/users/{user_id}/revoke-admin", { params: { path: { user_id: userId } } });
  if (!response.ok) throw await problem(response, "Could not change the role.");
}

export async function setUserDisabled(userId: string, disabled: boolean): Promise<void> {
  const { response } = disabled
    ? await api.POST("/api/v1/admin/users/{user_id}/disable", { params: { path: { user_id: userId } } })
    : await api.POST("/api/v1/admin/users/{user_id}/enable", { params: { path: { user_id: userId } } });
  if (!response.ok) throw await problem(response, "Could not change the account.");
}

export async function listPlans(): Promise<Plan[]> {
  const { data, response } = await api.GET("/api/v1/admin/plans");
  if (!data) throw await problem(response, "Could not load plans.");
  return data;
}

export async function updatePlan(planId: string, limits: PlanLimits): Promise<Plan> {
  const { data, response } = await api.PUT("/api/v1/admin/plans/{plan_id}", { params: { path: { plan_id: planId } }, body: { limits } });
  if (!data) throw await problem(response, "Could not save the plan.");
  return data;
}

export async function listFlags(): Promise<Flag[]> {
  const { data, response } = await api.GET("/api/v1/admin/flags");
  if (!data) throw await problem(response, "Could not load feature flags.");
  return data;
}

export async function updateFlag(key: string, enabled: boolean, audience: Flag["audience"]): Promise<void> {
  const { response } = await api.PUT("/api/v1/admin/flags/{key}", { params: { path: { key } }, body: { enabled, audience } });
  if (!response.ok) throw await problem(response, "Could not change the flag.");
}

export async function listJobs(): Promise<AdminJobs> {
  const { data, response } = await api.GET("/api/v1/admin/jobs");
  if (!data) throw await problem(response, "Could not load jobs.");
  return data;
}

export async function retryJob(jobId: string): Promise<void> {
  const { response } = await api.POST("/api/v1/admin/jobs/{job_id}/retry", { params: { path: { job_id: jobId } } });
  if (!response.ok) throw await problem(response, "Could not retry the job.");
}

export async function listModels(): Promise<ModelEntry[]> {
  const { data, response } = await api.GET("/api/v1/admin/models");
  if (!data) throw await problem(response, "Could not load models.");
  return data.items;
}

export async function updateModel(task: string, version: number, body: ModelUpdate): Promise<ModelEntry> {
  const { data, response } = await api.PUT("/api/v1/admin/models/{task}", {
    params: { path: { task }, header: { "If-Match": String(version) } },
    body,
  });
  if (!data) throw await problem(response, "Could not save the model.");
  return data;
}
