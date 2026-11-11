import { useQuery } from "@tanstack/react-query";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useMemo } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { getFileUrl, viewerKeys } from "./api";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

/** Page 1 of the sanitized copy, for the processing page (spec 008 AC10, mockup). */
export default function PdfPreview({ paperId, width }: { paperId: string; width: number }) {
  const file = useQuery({ queryKey: viewerKeys.fileUrl(paperId), queryFn: () => getFileUrl(paperId), retry: 6, retryDelay: 1500, staleTime: 4 * 60_000 });
  const options = useMemo(() => ({ disableAutoFetch: true, isEvalSupported: false }), []);
  if (!file.data) return null;
  return (
    <div aria-label="Page 1 preview" role="img" className="overflow-hidden rounded-md border border-border bg-surface">
      <Document file={file.data} options={options} loading="" error="" suspense={false}>
        <Page pageNumber={1} width={width} renderAnnotationLayer={false} renderTextLayer={false} loading="" />
      </Document>
    </div>
  );
}
