import { Dialog, buttonPrimary, buttonSecondary } from "@/components/dialog/Dialog";

import type { useUploadFlow } from "./useUploadFlow";

/** Spec 019 AC8: the uploaded PDF is already in Recently deleted; the reader chooses. */
export function InTrashDialog({ flow }: { flow: ReturnType<typeof useUploadFlow> }) {
  const found = flow.binned;
  if (!found) return null;
  return (
    <Dialog
      open
      title="This paper is in Recently deleted"
      onClose={flow.dismissBinned}
      footer={
        <>
          <button type="button" disabled={flow.resolving} onClick={flow.uploadAsNew} className={buttonSecondary}>Upload as new</button>
          <button type="button" disabled={flow.resolving} onClick={flow.restoreBinned} className={buttonPrimary}>Restore</button>
        </>
      }
    >
      <p>
        <span className="font-medium">{found.title}</span> was deleted recently. Restore it with its summaries, chats and notes, or upload it as a new paper and delete the old one for good.
      </p>
    </Dialog>
  );
}
