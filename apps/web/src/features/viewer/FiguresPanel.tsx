import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Crosshair, FileImage, Loader2, RotateCcw, Sparkles, Table2 } from "lucide-react";

import { Loading, ListRowSkeleton } from "@/components/feedback/Skeleton";
import { toast } from "@/components/status/toast";

import {
  describeFigure,
  elementKeys,
  getElements,
  getFigureImage,
  retryEnrichment,
  type FigureEl,
  type TableEl,
} from "./api";
import type { PageBox } from "./citation-context";
import { EnrichProgress } from "./EnrichProgress";

type Show = (page: number, box: PageBox, label: string) => void;

function TableView({ table }: { table: TableEl }) {
  const head = table.cells.slice(0, table.header_rows);
  const body = table.cells.slice(table.header_rows);
  return (
    <div className="max-h-80 overflow-auto rounded-md border border-border">
      <table className="w-full border-collapse text-sm">
        {table.caption && <caption className="sr-only">{table.caption}</caption>}
        <thead className="sticky top-0 bg-muted">
          {head.map((row, r) => (
            <tr key={r}>
              {row.map((cell, c) => (
                <th key={c} scope="col" className="border-b border-border px-2 py-1.5 text-left font-medium whitespace-nowrap">
                  {cell}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {body.map((row, r) => (
            <tr key={r} className="border-b border-border last:border-0">
              {row.map((cell, c) => (
                <td key={c} className="px-2 py-1.5 align-top tabular-nums">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FigureImage({ paperId, figure }: { paperId: string; figure: FigureEl }) {
  const image = useQuery({
    queryKey: elementKeys.image(paperId, figure.id),
    queryFn: () => getFigureImage(paperId, figure.id),
    enabled: figure.has_image,
    staleTime: 4 * 60_000, // the link lasts 5 minutes
  });
  if (!figure.has_image || image.isError) {
    return <p className="rounded-md bg-muted p-4 text-sm text-text-secondary">The image is not available.</p>;
  }
  return image.data ? (
    <img src={image.data} alt={figure.caption ?? figure.label} loading="lazy" className="max-h-80 w-full rounded-md border border-border bg-surface object-contain" />
  ) : (
    <div aria-hidden className="h-40 animate-pulse rounded-md bg-muted motion-reduce:animate-none" />
  );
}

function Describe({ paperId, figure }: { paperId: string; figure: FigureEl }) {
  const client = useQueryClient();
  const run = useMutation({
    mutationFn: () => describeFigure(paperId, figure.id),
    onSuccess: () => void client.invalidateQueries({ queryKey: elementKeys.list(paperId) }),
    onError: (err) => toast.error(err.message),
  });
  const text = figure.description ?? run.data;
  if (text) {
    return (
      <div className="rounded-md bg-muted p-3 text-sm">
        <p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-text-secondary">
          <Sparkles aria-hidden className="size-3.5" />
          AI-generated description
        </p>
        <p>{text}</p>
      </div>
    );
  }
  return (
    <button
      type="button"
      disabled={run.isPending}
      onClick={() => { run.mutate(); }}
      className="inline-flex min-h-11 items-center gap-2 rounded-md border border-border px-3 text-sm hover:bg-muted disabled:opacity-50"
    >
      {run.isPending ? <Loader2 aria-hidden className="size-4 animate-spin motion-reduce:animate-none" /> : <Sparkles aria-hidden className="size-4" />}
      {run.isPending ? "Describing" : "Describe this figure"}
    </button>
  );
}

/**
 * Figures & tables for one paper (spec 009 AC2, AC5 to AC7): progress while the background
 * parse runs, then every table and figure in page order with a way to see it in the paper.
 */
export function FiguresPanel({ paperId, onShow }: { paperId: string; onShow: Show }) {
  const client = useQueryClient();
  const elements = useQuery({
    queryKey: elementKeys.list(paperId),
    queryFn: () => getElements(paperId),
    refetchInterval: (q) => (q.state.data?.status === "pending" || q.state.data?.status === "running" ? 3000 : false),
  });
  const retry = useMutation({
    mutationFn: () => retryEnrichment(paperId),
    onSuccess: () => void client.invalidateQueries({ queryKey: elementKeys.list(paperId) }),
    onError: (err) => toast.error(err.message),
  });

  if (elements.isPending) {
    return (
      <Loading label="Loading tables and figures">
        <ListRowSkeleton />
        <ListRowSkeleton />
      </Loading>
    );
  }
  if (elements.isError) {
    return (
      <div role="alert" className="p-2 text-sm">
        {elements.error.message}
        <button type="button" onClick={() => void elements.refetch()} className="ml-2 min-h-11 underline">Try again</button>
      </div>
    );
  }
  const data = elements.data;
  const running = data.status === "pending" || data.status === "running" || data.status === null;
  const items = [
    ...data.tables.map((t) => ({ kind: "table" as const, item: t })),
    ...data.figures.map((f) => ({ kind: "figure" as const, item: f })),
  ].sort((a, b) => a.item.page - b.item.page || a.item.box.y - b.item.box.y);

  return (
    <div className="flex flex-col gap-4">
      <div aria-live="polite" className="text-sm text-text-secondary">
        {running ? (
          <EnrichProgress
            done={data.pages_done}
            total={data.pages_total === null ? null : Math.min(data.pages_total, data.pages_parsed_limit)}
            secondsLeft={data.seconds_left}
          />
        ) : data.status === "failed" ? (
          <div role="alert" className="flex flex-wrap items-center gap-2">
            <span>Tables and figures could not be found this time. The paper, summary and chat still work.</span>
            <button type="button" disabled={retry.isPending} onClick={() => { retry.mutate(); }} className="inline-flex min-h-11 items-center gap-2 rounded-md border border-border px-3 hover:bg-muted disabled:opacity-50">
              <RotateCcw aria-hidden className="size-4" />
              Retry
            </button>
          </div>
        ) : (
          <p>
            {`${String(data.tables.length)} ${data.tables.length === 1 ? "table" : "tables"} and ${String(data.figures.length)} ${data.figures.length === 1 ? "figure" : "figures"}`}
            {data.pages_total !== null && data.pages_total > data.pages_parsed_limit
              ? `. Only the first ${String(data.pages_parsed_limit)} pages with tables or figures were checked.`
              : ""}
          </p>
        )}
      </div>

      {!running && items.length === 0 && data.status === "done" && (
        <p className="rounded-md bg-muted p-4 text-sm text-text-secondary">This paper has no tables or figures.</p>
      )}

      <ul aria-label="Tables and figures" className="flex flex-col gap-4">
        {items.map((entry) => {
          const { kind, item } = entry;
          return (
          <li key={item.id} className="flex flex-col gap-2 rounded-lg border border-border p-3">
            <div className="flex items-start gap-2">
              {kind === "table" ? <Table2 aria-hidden className="mt-0.5 size-4 shrink-0" /> : <FileImage aria-hidden className="mt-0.5 size-4 shrink-0" />}
              <div className="min-w-0 flex-1">
                <p className="font-medium">{`${item.label}, p. ${String(item.page)}`}</p>
                {item.caption && <p className="text-sm text-text-secondary">{item.caption}</p>}
              </div>
              <button
                type="button"
                aria-label={`Show ${item.label} in the paper`}
                title="Show in paper"
                onClick={() => { onShow(item.page, item.box, item.label); }}
                className="inline-flex size-11 shrink-0 items-center justify-center rounded-md hover:bg-muted"
              >
                <Crosshair aria-hidden className="size-5" />
              </button>
            </div>
            {entry.kind === "table" ? <TableView table={entry.item} /> : (
              <>
                <FigureImage paperId={paperId} figure={entry.item} />
                <Describe paperId={paperId} figure={entry.item} />
              </>
            )}
          </li>
          );
        })}
      </ul>
    </div>
  );
}
