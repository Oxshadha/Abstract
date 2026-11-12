/** Save a blob as a file the user downloads (no navigation, nothing left in memory). */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => { URL.revokeObjectURL(url); }, 0);
}

/** The filename from a Content-Disposition header, or the fallback. */
export function filenameFrom(disposition: string | null, fallback: string): string {
  const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition ?? "");
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      // fall through to the plain name
    }
  }
  const plain = /filename="([^"]+)"/i.exec(disposition ?? "");
  return plain?.[1] ?? fallback;
}
