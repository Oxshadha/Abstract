import { useQuery } from "@tanstack/react-query";

import { fetchHealth } from "@/api/health";

export function HomePage() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: false });
  const label = health.isPending ? "checking…" : health.data === "ok" ? "ok" : "unreachable";

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-4 p-6">
      <div className="flex items-center gap-3">
        <img src="/abstract-icon-light.svg" alt="" className="h-10 w-10" />
        <h1 className="text-3xl font-bold">Abstract.</h1>
      </div>
      <p>Research papers, made clear.</p>
      <p role="status" aria-live="polite">
        API status: <strong data-testid="api-status">{label}</strong>
      </p>
    </main>
  );
}
