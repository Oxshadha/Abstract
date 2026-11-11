import {
  createRootRoute,
  lazyRouteComponent,
  createRoute,
  createRouter,
  Outlet,
  type RouterHistory,
} from "@tanstack/react-router";

import { GatedAppShell } from "@/components/shell/GatedAppShell";
import { SignInPage, SignUpPage } from "@/routes/auth/AuthPages";
import {
  CollectionsPage,
  LibraryPage,
  NotFoundPage,
  SettingsPage,
  TemplatesPage,
} from "@/routes/app/pages";
import { HomePage } from "@/routes/HomePage";

const rootRoute = createRootRoute({ component: Outlet, notFoundComponent: NotFoundPage });
const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: "/", component: HomePage });
const appRoute = createRoute({ getParentRoute: () => rootRoute, path: "/app", component: GatedAppShell });
const signInRoute = createRoute({ getParentRoute: () => rootRoute, path: "/sign-in/$", component: SignInPage });
const signUpRoute = createRoute({ getParentRoute: () => rootRoute, path: "/sign-up/$", component: SignUpPage });
const libraryRoute = createRoute({ getParentRoute: () => appRoute, path: "/library", component: LibraryPage });
const collectionsRoute = createRoute({ getParentRoute: () => appRoute, path: "/collections", component: CollectionsPage });
const templatesRoute = createRoute({ getParentRoute: () => appRoute, path: "/templates", component: TemplatesPage });
const settingsRoute = createRoute({ getParentRoute: () => appRoute, path: "/settings", component: SettingsPage });
const workspaceRoute = createRoute({ getParentRoute: () => appRoute, path: "/papers/$paperId", component: lazyRouteComponent(() => import("@/routes/app/WorkspacePage")) });

const routeTree = rootRoute.addChildren([
  indexRoute,
  signInRoute,
  signUpRoute,
  appRoute.addChildren([libraryRoute, collectionsRoute, templatesRoute, settingsRoute, workspaceRoute]),
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
