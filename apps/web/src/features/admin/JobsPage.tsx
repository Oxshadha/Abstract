import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { useState } from "react";

import { ListRowSkeleton, Loading } from "@/components/feedback/Skeleton";
import { StatusPill } from "@/components/status/StatusPill";
import { toast } from "@/components/status/toast";

import { adminKeys, listJobs, retryJob, type AdminJob } from "./api";
import { count, when } from "./format";

const KINDS: Record<string, string> = { ingest: "Processing", ocr: "Text recognition", enrich: "Tables and figures", scan: "Malware scan", summary: "Summary" };

function JobRow({ job }: { job: AdminJob }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const retry = useMutation({
    mutationFn: () => retryJob(job.id),
    onSuccess: async () => {
      toast("Job queued again.");
      await queryClient.invalidateQueries({ queryKey: adminKeys.jobs });
    },
    onError: (e) => { toast(e.message); },
  });
  const label = KINDS[job.kind] ?? job.kind;
  return (
    <li className="flex min-w-0 flex-col gap-1 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="flex min-w-0 items-center gap-2">
            <span className="truncate font-medium">{label}</span>
            {job.stuck ? <StatusPill status="warning">Stuck</StatusPill> : <StatusPill status="error">{job.status === "enqueue_failed" ? "Not queued" : "Failed"}</StatusPill>}
          </p>
          <p className="truncate text-xs text-text-secondary">{`${job.owner_email ?? "Unknown"} · ${count(job.attempts)} attempts · ${when(job.at)}`}</p>
        </div>
        {job.retryable ? (
          <button type="button" aria-label={`Retry ${label} for ${job.owner_email ?? "this user"}`} disabled={retry.isPending} onClick={() => { retry.mutate(); }} className="inline-flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-muted disabled:opacity-50">
            <RotateCcw aria-hidden className="size-5" />
          </button>
        ) : (
          <span className="shrink-0 text-xs text-text-secondary">Retried by the owner</span>
        )}
      </div>
      {job.last_error && (
        <button type="button" aria-expanded={open} onClick={() => { setOpen(!open); }} className={`min-h-9 text-left font-mono text-xs text-text-secondary ${open ? "break-all whitespace-pre-wrap" : "truncate"}`}>
          {job.last_error}
        </button>
      )}
    </li>
  );
}

/** Admin jobs (spec 011 AC8): failed, never-queued and stuck jobs, with an audited retry. */
export function JobsPage() {
  const jobs = useQuery({ queryKey: adminKeys.jobs, queryFn: listJobs, refetchInterval: 15_000 });
  if (jobs.isPending) return <Loading label="Loading jobs"><ListRowSkeleton /></Loading>;
  if (jobs.isError) return <p role="alert">{jobs.error.message}</p>;
  const c = jobs.data.counts;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-text-secondary">
        {`${count(c.queued ?? 0)} queued · ${count(c.held ?? 0)} waiting for a slot · ${count(c.running ?? 0)} running · ${count(c.failed_24h ?? 0)} failed today`}
      </p>
      {jobs.data.items.length === 0 ? (
        <p className="rounded-lg border border-border bg-surface p-4 text-sm text-text-secondary">No failed or stuck jobs.</p>
      ) : (
        <ul aria-label="Jobs needing attention" className="flex flex-col divide-y divide-border rounded-lg border border-border bg-surface px-4">
          {jobs.data.items.map((j) => <JobRow key={j.id} job={j} />)}
        </ul>
      )}
    </div>
  );
}
