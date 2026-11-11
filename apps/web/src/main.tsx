import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./index.css";
import { initSentry } from "./observability/sentry";
import { AuthBoundary } from "./auth/AuthBoundary";
import { ErrorBoundary } from "./components/feedback/ErrorBoundary";
import { createQueryClient } from "./lib/queryClient";
import { router } from "./router";

initSentry();

const queryClient = createQueryClient();

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("#root element missing");

createRoot(rootElement).render(
  <StrictMode>
    <ErrorBoundary name="the app">
    <AuthBoundary>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </AuthBoundary>
    </ErrorBoundary>
  </StrictMode>,
);
