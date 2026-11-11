import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useRef, useState } from "react";

import { useOnline } from "@/components/feedback/useOnline";
import { toast } from "@/components/status/toast";

import { paperKeys } from "./api";
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

  const upload = useMutation({
    mutationFn: (file: File) => {
      controller.current = new AbortController();
      return uploadPaper(file, { onPhase: setPhase, onProgress: setProgress, signal: controller.current.signal });
    },
    onSuccess: async (result) => {
      // The new paper must show in the Library at once, not after the cached list expires.
      void queryClient.invalidateQueries({ queryKey: paperKeys.list });
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
  };
}
