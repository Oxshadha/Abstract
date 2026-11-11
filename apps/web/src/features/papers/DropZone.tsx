import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { FileText, FileUp, X } from "lucide-react";
import { useId, useRef, useState, type DragEvent } from "react";

import { FieldError } from "@/components/status/FieldError";
import { toast } from "@/components/status/toast";
import { useOnline } from "@/components/feedback/useOnline";

import { UploadCancelledError, uploadPaper, validatePdf, type UploadPhase } from "./upload";

const PHASE_LABEL: Record<UploadPhase, string> = {
  checking: "Preparing your file",
  uploading: "Uploading",
  starting: "Starting processing",
};

/**
 * Upload a research paper (spec 004 AC2): drag and drop or file picker, checks before upload,
 * direct upload to storage with progress and cancel, then the processing page.
 */
export function DropZone({ compact = false }: { compact?: boolean }) {
  const navigate = useNavigate();
  const online = useOnline();
  const input = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | null>(null);
  const errorId = useId();
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<UploadPhase | null>(null);
  const [progress, setProgress] = useState(0);
  const [fileName, setFileName] = useState("");

  const upload = useMutation({
    mutationFn: (file: File) => {
      controller.current = new AbortController();
      return uploadPaper(file, { onPhase: setPhase, onProgress: setProgress, signal: controller.current.signal });
    },
    onSuccess: async (result) => {
      if (result.duplicate) toast("This paper is already in your library.");
      await navigate({
        // Step 02 (spec 006 AC2): pick a template; a duplicate goes to its processing page.
        to: result.duplicate ? "/app/papers/$paperId/processing" : "/app/papers/$paperId/template",
        params: { paperId: result.paper.id },
      });
    },
    onError: (err) => {
      if (err instanceof UploadCancelledError) toast("Upload cancelled.");
      else setError(err.message);
    },
    onSettled: () => {
      setPhase(null);
      setProgress(0);
      controller.current = null;
    },
  });

  const start = (file: File | undefined) => {
    if (!file || upload.isPending) return;
    const invalid = validatePdf(file);
    setError(invalid);
    if (invalid) return;
    setFileName(file.name);
    upload.mutate(file);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length > 1) {
      setError("Please upload one PDF at a time.");
      return;
    }
    start(event.dataTransfer.files[0]);
  };

  const busy = upload.isPending && phase !== null;
  const percent = Math.round(progress * 100);

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        if (!busy) setDragging(true);
      }}
      onDragLeave={() => {
        setDragging(false);
      }}
      onDrop={onDrop}
      className={`flex flex-col items-center gap-3 rounded-xl border-2 border-dashed px-4 text-center ${compact ? "py-6" : "py-10"} ${dragging ? "border-text bg-muted" : "border-border-strong bg-surface"}`}
    >
      {busy ? (
        <div className="flex w-full max-w-md flex-col items-center gap-3" aria-live="polite">
          <FileText aria-hidden className="size-10 text-text-secondary" />
          <p className="max-w-full truncate font-medium" title={fileName}>
            {fileName}
          </p>
          <p className="text-sm text-text-secondary">
            {PHASE_LABEL[phase]}
            {phase === "uploading" ? ` ${String(percent)}%` : ""}
          </p>
          <div
            role="progressbar"
            aria-label="Upload progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={phase === "uploading" ? percent : undefined}
            className="h-2 w-full overflow-hidden rounded-pill bg-muted"
          >
            <div
              className="h-full rounded-pill bg-primary transition-[width] motion-reduce:transition-none"
              style={{ width: `${String(phase === "uploading" ? percent : phase === "starting" ? 100 : 5)}%` }}
            />
          </div>
          {phase !== "starting" && (
            <button
              type="button"
              onClick={() => controller.current?.abort()}
              className="inline-flex min-h-11 items-center gap-2 rounded-pill border border-border px-4 hover:bg-muted"
            >
              <X aria-hidden className="size-4" />
              Cancel upload
            </button>
          )}
        </div>
      ) : (
        <>
          <FileUp aria-hidden className="size-12" />
          <h2 className="font-display text-xl font-bold">Upload a research paper</h2>
          <p className="text-text-secondary">Drop a PDF here or choose a file to get a structured summary.</p>
          <button
            type="button"
            disabled={!online}
            aria-describedby={error ? errorId : undefined}
            onClick={() => input.current?.click()}
            className="inline-flex min-h-11 items-center gap-2 rounded-pill bg-primary px-5 font-medium text-primary-text disabled:opacity-50"
          >
            <FileText aria-hidden className="size-5" />
            Choose PDF
          </button>
          <input
            ref={input}
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            tabIndex={-1}
            aria-hidden
            onChange={(event) => {
              start(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
          <p className="text-sm text-text-secondary">PDF up to 50 MB. Supports academic papers, reports, and articles.</p>
          <FieldError id={errorId} message={error} />
        </>
      )}
    </div>
  );
}
