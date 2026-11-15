import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useRef, useState } from "react";

import { useOnline } from "@/components/feedback/useOnline";
import { toast } from "@/components/status/toast";

import { deleteForever, restorePaper } from "@/features/library/api";

import { finalizeUpload, paperKeys, PaperInTrashError, type FinalizeResponse } from "./api";
import { UploadCancelledError, uploadPaper, validatePdf, type UploadPhase } from "./upload";

/** Upload state shared by the drop zone and the Library's "Add Paper" button (013 AC1). */
export function useUploadFlow() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const online = useOnline();
  const controller = useRef<AbortController | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<UploadPhase | null>(null);
  const [progress, setProgress] = useState(0);
  const [fileName, setFileName] = useState("");
  const [binned, setBinned] = useState<PaperInTrashError | null>(null);

  const opened = async (result: FinalizeResponse) => {
    // The new paper must show in the Library at once, not after the cached list expires.
    void queryClient.invalidateQueries({ queryKey: paperKeys.list });
    if (result.duplicate) toast("This paper is already in your library.");
    await navigate({
      // Step 02 (spec 006 AC2): pick a template; a duplicate goes to its processing page.
      to: result.duplicate ? "/app/papers/$paperId/processing" : "/app/papers/$paperId/template",
      params: { paperId: result.paper.id },
    });
  };

  // Spec 019 AC8: Restore brings the binned paper back (not counted as an upload); Upload as new
  // deletes it for good and finishes this same upload as a normal one.
  const resolveBinned = useMutation({
    mutationFn: async ({ found, choice }: { found: PaperInTrashError; choice: "restore" | "new" }) => {
      if (choice === "restore") return { kind: "restored" as const, paper: await restorePaper(found.paperId) };
      await deleteForever(found.paperId);
      return { kind: "new" as const, result: await finalizeUpload(found.uploadId, crypto.randomUUID()) };
    },
    onSuccess: async (outcome) => {
      setBinned(null);
      void queryClient.invalidateQueries({ queryKey: ["papers"] });
      if (outcome.kind === "restored") {
        toast("Paper restored from Recently deleted.");
        const { paper } = outcome;
        await navigate({ to: paper.status === "ready" ? "/app/papers/$paperId" : "/app/papers/$paperId/processing", params: { paperId: paper.id } });
      } else await opened(outcome.result);
    },
    onError: (err) => {
      setBinned(null);
      setError(err.message);
    },
  });

  const upload = useMutation({
    mutationFn: (file: File) => {
      controller.current = new AbortController();
      return uploadPaper(file, { onPhase: setPhase, onProgress: setProgress, signal: controller.current.signal });
    },
    onSuccess: (result) => opened(result),
    onError: (err) => {
      if (err instanceof UploadCancelledError) toast("Upload cancelled.");
      else if (err instanceof PaperInTrashError) setBinned(err);
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

  const dropped = (files: FileList) => {
    if (files.length > 1) {
      setError("Please upload one PDF at a time.");
      return;
    }
    start(files[0]);
  };
  const busy = upload.isPending && phase !== null;
  return {
    start,
    dropped,
    busy,
    online,
    error,
    phase,
    fileName,
    percent: Math.round(progress * 100),
    cancel: () => controller.current?.abort(),
    binned,
    resolving: resolveBinned.isPending,
    restoreBinned: () => { if (binned) resolveBinned.mutate({ found: binned, choice: "restore" }); },
    uploadAsNew: () => { if (binned) resolveBinned.mutate({ found: binned, choice: "new" }); },
    dismissBinned: () => { setBinned(null); },
  };
}
