import {
  createRootRoute,
  lazyRouteComponent,
  createRoute,
  createRouter,
  Outlet,
  redirect,
  type RouterHistory,
} from "@tanstack/react-router";

import { GatedAppShell } from "@/components/shell/GatedAppShell";
import { SignInPage, SignUpPage } from "@/routes/auth/AuthPages";
import { parseLibrarySearch } from "@/features/library/search-params";
import {
  LibraryPage,
  NotFoundPage,
} from "@/routes/app/pages";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { HomePage } from "@/routes/HomePage";

const rootRoute = createRootRoute({ component: Outlet, notFoundComponent: NotFoundPage });
const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: HomePage });
const appRoute = createRoute({ getParentRoute: () => rootRoute, path: "/app", component: GatedAppShell });
const signInRoute = createRoute({ getParentRoute: () => rootRoute, path: "/sign-in/$", component: SignInPage });
const signUpRoute = createRoute({ getParentRoute: () => rootRoute, path: "/sign-up/$", component: SignUpPage });
// Filters, sort and the open collection live in the URL (spec 013 AC3, AC7).
// Home (D83): upload plus the papers opened most recently; /app lands here.
const homeRoute = createRoute({ getParentRoute: () => appRoute, path: "/home", component: lazyRouteComponent(() => import("@/features/library/HomePage")) });
const appIndexRoute = createRoute({ getParentRoute: () => appRoute, path: "/", beforeLoad: () => redirect({ to: "/app/home", throw: true }) });
const libraryRoute = createRoute({ getParentRoute: () => appRoute, path: "/library", component: LibraryPage, validateSearch: parseLibrarySearch });
// Collections are folders in the Library sidebar now (D82); old links land on the Library.
const collectionsRoute = createRoute({ getParentRoute: () => appRoute, path: "/collections", beforeLoad: () => redirect({ to: "/app/library", throw: true }) });
const templatesRoute = createRoute({ getParentRoute: () => appRoute, path: "/templates", component: lazyRouteComponent(() => import("@/features/templates/TemplatesRoute"), "TemplatesIndex") });
// Template builder (spec 010): a new template, or one of the user's own.
const newTemplateRoute = createRoute({ getParentRoute: () => appRoute, path: "/templates/new", component: lazyRouteComponent(() => import("@/features/templates/TemplatesRoute"), "NewTemplate") });
const editTemplateRoute = createRoute({ getParentRoute: () => appRoute, path: "/templates/$templateId", component: lazyRouteComponent(() => import("@/features/templates/TemplatesRoute"), "EditTemplate") });
const settingsRoute = createRoute({ getParentRoute: () => appRoute, path: "/settings", component: SettingsPage });
// Admin (spec 011): platform admins only; loaded on demand so other users never download it.
const adminRoute = createRoute({ getParentRoute: () => appRoute, path: "/admin", component: lazyRouteComponent(() => import("@/features/admin/AdminLayout"), "AdminLayout") });
const adminOverviewRoute = createRoute({ getParentRoute: () => adminRoute, path: "/", component: lazyRouteComponent(() => import("@/features/admin/OverviewPage"), "OverviewPage") });
const adminUsersRoute = createRoute({ getParentRoute: () => adminRoute, path: "/users", component: lazyRouteComponent(() => import("@/features/admin/UsersPage"), "UsersPage") });
const adminPlansRoute = createRoute({ getParentRoute: () => adminRoute, path: "/plans", component: lazyRouteComponent(() => import("@/features/admin/PlansPage"), "PlansPage") });
const adminModelsRoute = createRoute({ getParentRoute: () => adminRoute, path: "/models", component: lazyRouteComponent(() => import("@/features/admin/ModelsPage"), "ModelsPage") });
const adminFlagsRoute = createRoute({ getParentRoute: () => adminRoute, path: "/flags", component: lazyRouteComponent(() => import("@/features/admin/FlagsPage"), "FlagsPage") });
const adminJobsRoute = createRoute({ getParentRoute: () => adminRoute, path: "/jobs", component: lazyRouteComponent(() => import("@/features/admin/JobsPage"), "JobsPage") });
const templateRoute = createRoute({ getParentRoute: () => appRoute, path: "/papers/$paperId/template", component: lazyRouteComponent(() => import("@/features/summaries/TemplateStep")) });
const processingRoute = createRoute({ getParentRoute: () => appRoute, path: "/papers/$paperId/processing", component: lazyRouteComponent(() => import("@/features/papers/ProcessingPage")) });
// A search passage opens the paper at its page with the passage highlighted (spec 013 AC8).
const workspaceRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/papers/$paperId",
  component: lazyRouteComponent(() => import("@/routes/app/WorkspacePage")),
  validateSearch: (search: Record<string, unknown>): { page?: number; quote?: string } => {
    const page = Number(search.page);
    const quote = typeof search.quote === "string" ? search.quote.slice(0, 500) : undefined;
    return Number.isInteger(page) && page > 0 ? { page, ...(quote ? { quote } : {}) } : {};
  },
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  signInRoute,
  signUpRoute,
  appRoute.addChildren([appIndexRoute, homeRoute, libraryRoute, collectionsRoute, templatesRoute, newTemplateRoute, editTemplateRoute, settingsRoute, adminRoute.addChildren([adminOverviewRoute, adminUsersRoute, adminPlansRoute, adminModelsRoute, adminFlagsRoute, adminJobsRoute]), templateRoute, processingRoute, workspaceRoute]),
]);

export function createAppRouter(history?: RouterHistory) {
  return createRouter({ routeTree, history, defaultNotFoundComponent: NotFoundPage });
}

export const router = createAppRouter();

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
