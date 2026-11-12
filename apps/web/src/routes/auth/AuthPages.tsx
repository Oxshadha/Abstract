import { Navigate } from "@tanstack/react-router";
import { FileText, Layers, MessageSquare } from "lucide-react";

import { AuthPanel } from "@/auth/AuthPanel";
import { useAuthState } from "@/auth/state";
import { Logo } from "@/components/brand/Logo";

const FEATURES = [
  { Icon: Layers, title: "Structured summaries", text: "Get clear, organized overviews from any paper." },
  { Icon: MessageSquare, title: "Ask with citations", text: "Answers grounded in the paper, with page references." },
  { Icon: FileText, title: "Custom templates", text: "Define what to extract and reuse it across papers." },
];

/** Full-page sign-in/up fallback with the split-screen mockup layout (D45). */
function AuthPage({ mode }: { mode: "sign-in" | "sign-up" }) {
  const { status } = useAuthState();
  if (status === "signed-in") return <Navigate to="/app/home" />;
  return (
    <div className="grid min-h-dvh bg-bg text-text lg:grid-cols-2">
      <section className="hidden flex-col justify-center gap-8 p-12 lg:flex">
        <Logo />
        <h1 className="text-5xl font-bold tracking-tight">Research papers, made clear.</h1>
        <p className="max-w-lg text-lg text-text-secondary">
          Turn complex papers into structured summaries, explore findings, and ask questions grounded in the source.
        </p>
        <ul className="grid gap-6 sm:grid-cols-3">
          {FEATURES.map(({ Icon, title, text }) => (
            <li key={title} className="flex flex-col gap-2">
              <Icon aria-hidden className="size-6" />
              <span className="font-medium">{title}</span>
              <span className="text-sm text-text-secondary">{text}</span>
            </li>
          ))}
        </ul>
      </section>
      <section className="flex items-center justify-center p-6">
        <div className="w-full max-w-md rounded-xl bg-surface p-8 shadow-card">
          <AuthPanel mode={mode} routing="path" />
        </div>
      </section>
    </div>
  );
}

export function SignInPage() {
  return <AuthPage mode="sign-in" />;
}

export function SignUpPage() {
  return <AuthPage mode="sign-up" />;
}
