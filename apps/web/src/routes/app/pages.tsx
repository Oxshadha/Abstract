import { LibraryView } from "@/features/library/LibraryView";


function PageHeader({ title, description }: { title: string; description: string }) {
  return (
    <header className="px-4 pt-6 pb-4 md:px-8">
      <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
      <p className="mt-1 text-text-secondary">{description}</p>
    </header>
  );
}

export function LibraryPage() {
  return <LibraryView />;
}

export function TemplatesPage() {
  return <PageHeader title="Templates" description="Choose or design how summaries are structured." />;
}

export function SettingsPage() {
  return <PageHeader title="Settings" description="Account, appearance, and workspace preferences." />;
}

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-md px-4 py-16 text-center">
      <h1 className="text-2xl font-bold">Page not found</h1>
      <p className="mt-2 text-text-secondary">The page you are looking for does not exist or has moved.</p>
      <a href="/app/home" className="mt-6 inline-flex min-h-11 items-center rounded-pill bg-primary px-5 text-primary-text">
        Go home
      </a>
    </div>
  );
}
