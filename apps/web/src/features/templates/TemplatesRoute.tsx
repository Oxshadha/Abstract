import { useParams } from "@tanstack/react-router";

import { TemplateBuilder } from "./TemplateBuilder";
import { TemplatesPage } from "./TemplatesPage";

export function TemplatesIndex() {
  return <TemplatesPage />;
}

export function NewTemplate() {
  return <TemplateBuilder />;
}

export function EditTemplate() {
  const { templateId } = useParams({ from: "/app/templates/$templateId" });
  // Remount per template so the form never mixes two templates' state.
  return <TemplateBuilder key={templateId} templateId={templateId} />;
}
