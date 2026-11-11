/** Inline form error (D44): announced to screen readers, linked via aria-describedby. */
export function FieldError({ id, message }: { id: string; message?: string | null }) {
  if (!message) return null;
  return (
    <p id={id} role="alert" className="mt-1 text-sm text-error">
      {message}
    </p>
  );
}
