import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "@tanstack/react-router";
import { lazy, Suspense, useEffect } from "react";

const PdfPreview = lazy(() => import("@/features/viewer/PdfPreview"));
import { Check, ChevronLeft, Circle, ExternalLink, FileText, Layers, Loader2, X } from "lucide-react";

import { Loading, SummaryCardSkeleton } from "@/components/feedback/Skeleton";
import { StatusPill } from "@/components/status/StatusPill";

import { getPaper, paperKeys, type PaperStatus } from "./api";
import { formatBytes, formatPages } from "./format";
import { isFinished, useProcessingStatus } from "./progress";

type Step = PaperStatus["steps"][number];

const STEPS: Record<Step["key"], { label: string; detail: string }> = {
  uploading: { label: "Uploading", detail: "Sending your PDF securely." },
  extracting: { label: "Extracting text", detail: "Reading and extracting content from the PDF." },
  sections: {
    label: "Identifying sections",
    detail: "Detecting key parts (Abstract, Introduction, Methodology, and more).",
  },
  indexing: { label: "Indexing for chat", detail: "Preparing the paper so you can ask questions about it." },
  ocr: { label: "Reading scanned pages", detail: "Recognizing text on pages that are images." },
  summary: {
    label: "Building summary",
    detail: "Generating a structured summary based on the selected template.",
  },
  citations: { label: "Finding citations", detail: "Linking key claims to pages in the paper." },
};

const STATE_TEXT: Record<Step["state"], string> = {
  done: "Completed",
  active: "In progress",
  pending: "Pending",
  failed: "Failed",
};

function StepIcon({ state }: { state: Step["state"] }) {
  if (state === "done")
    return (
      <span className="flex size-7 items-center justify-center rounded-pill bg-primary text-primary-text">
        <Check aria-hidden className="size-4" />
      </span>
    );
  if (state === "active")
    return <Loader2 aria-hidden className="size-7 animate-spin text-text motion-reduce:animate-none" />;
  if (state === "failed")
    return (
      <span className="flex size-7 items-center justify-center rounded-pill border-2 border-text">
        <X aria-hidden className="size-4" />
      </span>
    );
  return <Circle aria-hidden className="size-7 text-border-strong" />;
}

function Steps({ status }: { status: PaperStatus }) {
  const steps = status.steps.filter((s) => s.key !== "uploading");
  return (
    <ol className="flex flex-col">
      {steps.map((step, index) => (
        <li key={step.key} className="relative flex gap-4 pb-6 last:pb-0">
          {index < steps.length - 1 && (
            <span aria-hidden className="absolute top-8 bottom-0 left-3.5 w-px bg-border" />
          )}
          <StepIcon state={step.state} />
          <div className="flex min-w-0 flex-1 items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <p className="font-display text-lg font-bold">{STEPS[step.key].label}</p>
              <p className="text-sm text-text-secondary">{STEPS[step.key].detail}</p>
              {step.state === "active" && step.progress != null && (
                <div
                  role="progressbar"
                  aria-label={`${STEPS[step.key].label} progress`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(step.progress * 100)}
                  className="mt-2 h-1.5 w-full overflow-hidden rounded-pill bg-muted"
                >
                  <div
                    className="h-full rounded-pill bg-primary transition-[width] motion-reduce:transition-none"
                    style={{ width: `${String(Math.round(step.progress * 100))}%` }}
                  />
                </div>
              )}
            </div>
            <span className="shrink-0 pt-1 text-sm whitespace-nowrap text-text-secondary">
              {step.state === "active" && step.progress != null
                ? `${String(Math.round(step.progress * 100))}%`
                : STATE_TEXT[step.state]}
            </span>
          </div>
        </li>
      ))}
    </ol>
  );
}

/** Live label for assistive technology: one sentence that changes as processing advances. */
function announcement(status: PaperStatus): string {
  if (status.status === "failed") return "Processing failed.";
  if (isFinished(status)) return "Your paper is ready.";
  const active = status.steps.find((s) => s.state === "active");
  const ready = status.chat_available ? " Chat is available." : "";
  return active ? `${STEPS[active.key].label}.${ready}` : `Processing.${ready}`;
}

/** Processing page (spec 004 AC12, Processing mockup). Keyed by paper so state resets. */
export default function ProcessingPage() {
  const { paperId } = useParams({ from: "/app/papers/$paperId/processing" });
  return <Processing key={paperId} paperId={paperId} />;
}

function Processing({ paperId }: { paperId: string }) {
  const paper = useQuery({ queryKey: paperKeys.detail(paperId), queryFn: () => getPaper(paperId) });
  const status = useProcessingStatus(paperId);
  const data = status.data;
  const failed = data?.status === "failed";
  const finished = data ? isFinished(data) : false;
  const queryClient = useQueryClient();
  useEffect(() => {
    // Pages and the extracted title are known only after processing: refresh them once.
    if (finished) void queryClient.invalidateQueries({ queryKey: paperKeys.detail(paperId), exact: true });
  }, [finished, paperId, queryClient]);
  const title = paper.data?.title ?? paper.data?.filename ?? "Your paper";

  return (
    <div className="flex flex-col gap-6 px-4 pt-4 pb-10 md:px-8">
      <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 text-sm text-text-secondary">
        <Link to="/app/library" className="inline-flex min-h-11 items-center gap-1 hover:text-text">
          <ChevronLeft aria-hidden className="size-4" />
          Library
        </Link>
        <span aria-hidden>/</span>
        <span className="truncate text-text" aria-current="page">
          {title}
        </span>
      </nav>

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-bold tracking-tight md:text-4xl">
            {failed ? "We could not process this paper" : "Processing your paper"}
          </h1>
          <p className="mt-1 text-text-secondary">
            {failed
              ? "Nothing else in your library was affected."
              : "We are analyzing your paper. Chat becomes available as soon as the text is indexed."}
          </p>
        </div>
        {data?.chat_available ? (
          <Link
            to="/app/papers/$paperId"
            params={{ paperId }}
            className="inline-flex min-h-11 items-center gap-2 rounded-pill bg-primary px-5 font-medium text-primary-text"
          >
            <ExternalLink aria-hidden className="size-5" />
            Open workspace
          </Link>
        ) : (
          <span
            aria-disabled="true"
            className="inline-flex min-h-11 items-center gap-2 rounded-pill border border-border px-5 text-text-secondary"
          >
            <ExternalLink aria-hidden className="size-5" />
            Open workspace
          </span>
        )}
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-label="File" className="self-start rounded-xl border border-border bg-surface p-4 shadow-card">
          <div className="flex items-center gap-3">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-md bg-muted">
              <FileText aria-hidden className="size-5" />
            </span>
            <div className="min-w-0">
              <p className="truncate font-medium" title={paper.data?.filename}>
                {paper.data?.filename ?? " "}
              </p>
              <p className="text-sm text-text-secondary">
                {[paper.data?.pages ? formatPages(paper.data.pages) : null,
                  paper.data ? formatBytes(paper.data.size_bytes) : null]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </div>
          </div>
          <div className="mt-4">
            <Suspense fallback={null}>
              <PdfPreview paperId={paperId} width={420} />
            </Suspense>
          </div>
        </section>

        <section aria-labelledby="progress-heading" className="rounded-xl border border-border bg-surface p-4 shadow-card md:p-6">
          <div className="mb-6 flex items-start gap-4">
            <span className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-muted">
              <Layers aria-hidden className="size-6" />
            </span>
            <div>
              <h2 id="progress-heading" className="font-display text-xl font-bold">
                {failed ? "Processing stopped" : data && isFinished(data) ? "Your paper is ready." : "Your paper is being analyzed."}
              </h2>
              <p className="text-text-secondary">
                {data && isFinished(data) && !failed
                  ? "Open the workspace to read and ask questions about it."
                  : "This may take a few moments depending on the document size."}
              </p>
            </div>
          </div>
          {data ? (
            <>
              <p className="sr-only" aria-live="polite">
                {announcement(data)}
              </p>
              <Steps status={data} />
              {failed && data.error_message && (
                <div className="mt-6 flex flex-col items-start gap-2">
                  <StatusPill status="error">Failed</StatusPill>
                  <p>{data.error_message}</p>
                  <Link to="/app/library" className="min-h-11 py-2 underline">
                    Back to your library
                  </Link>
                </div>
              )}
            </>
          ) : status.isError ? (
            <p role="alert">{status.error.message}</p>
          ) : (
            <Loading label="Loading progress">
              <SummaryCardSkeleton />
            </Loading>
          )}
        </section>
      </div>
    </div>
  );
}
