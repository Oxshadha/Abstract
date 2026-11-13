import { ArrowRight, BookOpen, Check, Folder, ImageIcon, Layers, MessageSquare, Pause, Play, SlidersHorizontal, Upload, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";

import { LogoMark } from "@/components/brand/Logo";

import { looksSignedIn } from "./session-hint";

/*
 * The public landing page (spec 016, D93). Rendered to static HTML at build time and hydrated
 * in the browser, so it uses plain links (no router) and makes no API calls for visitors.
 */

const noSubscription = () => () => undefined; // sign-in does not change while on this page

const SIGN_UP = "/sign-up/";
const SIGN_IN = "/sign-in/";
const APP = "/app/library";

const primary =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-pill bg-primary px-5 font-medium text-primary-text hover:opacity-90";
const secondary =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-pill border border-border bg-surface px-5 font-medium text-text hover:bg-muted";

const STEPS: { n: number; title: string; text: string; Icon: LucideIcon }[] = [
  { n: 1, title: "Upload a paper", text: "Add a PDF from your device.", Icon: Upload },
  { n: 2, title: "Summarize and analyze", text: "Use a ready-made template or create your own.", Icon: Layers },
  { n: 3, title: "Explore and ask", text: "Read the summary, view figures, and ask questions with citations.", Icon: MessageSquare },
];

const FEATURES: { title: string; text: string; Icon: LucideIcon }[] = [
  { title: "Structured summaries", text: "Clear, organized overviews of any paper, each point linked to its page.", Icon: BookOpen },
  { title: "Understand figures", text: "Tables and figures found for you, explained and ready to ask about.", Icon: ImageIcon },
  { title: "Custom templates", text: "Define what to extract once and reuse it across papers.", Icon: SlidersHorizontal },
  { title: "Stay organized", text: "Collections, stars and search keep your research library in order.", Icon: Folder },
];

const FREE = [
  "20 papers a month",
  "100 questions a day",
  "Summaries with sources on every point",
  "Tables, figures and custom templates",
];

function Section({ id, title, intro, children }: { id: string; title: string; intro?: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-24 px-4 py-16 md:px-8 md:py-24">
      <div className="mx-auto flex max-w-6xl flex-col gap-10">
        <div className="flex flex-col gap-3 text-center">
          <h2 id={`${id}-title`} className="font-display text-3xl font-bold tracking-tight md:text-4xl">{title}</h2>
          {intro && <p className="mx-auto max-w-2xl text-lg text-text-secondary">{intro}</p>}
        </div>
        {children}
      </div>
    </section>
  );
}

/** Product screenshot (D93): real Workspace, light and dark, two widths, size reserved. */
function ProductShot() {
  return (
    <picture>
      <source media="(prefers-color-scheme: dark)" type="image/webp" srcSet="/landing/workspace-dark-960.webp 960w, /landing/workspace-dark-1600.webp 1600w" sizes="(min-width: 1200px) 1152px, 94vw" />
      <source type="image/webp" srcSet="/landing/workspace-light-960.webp 960w, /landing/workspace-light-1600.webp 1600w" sizes="(min-width: 1200px) 1152px, 94vw" />
      <img
        src="/landing/workspace-light-1600.webp"
        alt="The Abstract workspace: the paper Attention Is All You Need on the left, its structured summary with page sources in the middle, and a cited answer in Ask Abstract on the right."
        width={1600}
        height={1000}
        fetchPriority="high"
        decoding="async"
        className="h-auto w-full rounded-xl border border-border bg-surface shadow-overlay"
      />
    </picture>
  );
}

/**
 * The How it works demo (D94): a real recording of the Workspace, muted and looping. It loads
 * and plays only while on screen, can be paused (WCAG 2.2.2), and stays still for readers who
 * prefer reduced motion until they press play.
 */
function DemoVideo() {
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [paused, setPaused] = useState(false); // paused by the reader: never restart on scroll

  useEffect(() => {
    const el = video.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const reduced = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced || paused) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) void el.play().catch(() => undefined);
        else el.pause();
      },
      { threshold: 0.4 },
    );
    observer.observe(el);
    return () => { observer.disconnect(); };
  }, [paused]);

  return (
    <figure className="relative mx-auto w-full max-w-5xl">
      <video
        ref={video}
        muted
        loop
        playsInline
        preload="none"
        poster="/landing/demo-poster.webp"
        width={1280}
        height={800}
        aria-label="Demo: a question about the paper is answered with numbered sources, and a source opens Table 2 in the paper."
        onPlay={() => { setPlaying(true); }}
        onPause={() => { setPlaying(false); }}
        className="h-auto w-full rounded-xl border border-border bg-surface shadow-overlay"
      >
        <source src="/landing/demo.mp4" type="video/mp4" />
      </video>
      <button
        type="button"
        aria-label={playing ? "Pause the demo" : "Play the demo"}
        onClick={() => {
          const el = video.current;
          if (!el) return;
          if (el.paused) {
            setPaused(false);
            void el.play().catch(() => undefined);
          } else {
            setPaused(true);
            el.pause();
          }
        }}
        className="absolute bottom-3 left-3 inline-flex size-11 items-center justify-center rounded-pill border border-border bg-surface/90 text-text shadow-card backdrop-blur"
      >
        {playing ? <Pause aria-hidden className="size-5" /> : <Play aria-hidden className="size-5" />}
      </button>
    </figure>
  );
}

export function LandingPage() {
  // False while prerendering and hydrating, so the static HTML is the same for everyone; the
  // browser's own value right after (AC5, AC7).
  const signedIn = useSyncExternalStore(noSubscription, looksSignedIn, () => false);

  return (
    <div className="min-h-dvh bg-bg text-text">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-surface focus:p-2">Skip to content</a>
      <header className="sticky top-0 z-40 border-b border-border bg-bg/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center gap-2 px-4 py-3 sm:gap-4 md:px-8">
          {/* Phones: the app's own phone header size (D86); the visible name is the link's name. */}
          <a href="/" className="inline-flex min-h-11 shrink-0 items-center gap-1.5 sm:gap-2">
            <LogoMark className="size-7 sm:size-8" />
            <span className="font-display text-xl font-bold tracking-tight sm:text-2xl">abstract.</span>
          </a>
          <nav aria-label="Sections" className="ml-auto hidden items-center gap-1 md:flex">
            {[["#features", "Features"], ["#how", "How it works"], ["#plans", "Plans"]].map(([href, label]) => (
              <a key={href} href={href} className="inline-flex min-h-11 items-center rounded-md px-3 text-text-secondary hover:text-text">{label}</a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1.5 sm:gap-2 md:ml-4">
            {signedIn ? (
              <a href={APP} className={`${primary} px-3 text-sm whitespace-nowrap sm:px-4 sm:text-base`}>Open your library</a>
            ) : (
              <>
                <a href={SIGN_IN} className={`${secondary} px-3 text-sm whitespace-nowrap sm:px-4 sm:text-base`}>Log in</a>
                <a href={SIGN_UP} className={`${primary} px-3 text-sm whitespace-nowrap sm:px-4 sm:text-base`}>Get started</a>
              </>
            )}
          </div>
        </div>
      </header>

      <main id="main">
        {/* Hero (AC1): centred, then the real product (D93). */}
        <section aria-labelledby="hero-title" className="relative overflow-hidden px-4 pt-14 md:px-8 md:pt-20">
          <div aria-hidden className="pointer-events-none absolute inset-x-0 top-40 -z-0 hidden justify-between opacity-60 lg:flex">
            <LogoMark className="size-72 -translate-x-24 rotate-[-8deg] opacity-10" />
            <LogoMark className="size-80 translate-x-24 rotate-[10deg] opacity-10" />
          </div>
          <div className="relative mx-auto flex max-w-5xl flex-col items-center gap-6 text-center">
            <span className="rounded-pill bg-muted px-3 py-1 text-sm">AI for research</span>
            <h1 id="hero-title" className="font-display text-4xl font-bold tracking-tight text-balance sm:text-5xl md:text-7xl">Research papers, made clear.</h1>
            <p className="max-w-2xl text-lg text-text-secondary md:text-xl">
              Turn complex papers into structured summaries, explore key findings, and ask questions grounded in the source.
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              <a href={signedIn ? APP : SIGN_UP} className={`${primary} px-6`}>
                {signedIn ? "Open your library" : "Get started"}
                <ArrowRight aria-hidden className="size-5" />
              </a>
              <a href="#how" className={`${secondary} px-6`}>
                <Play aria-hidden className="size-4" />
                See how it works
              </a>
            </div>
            <ul aria-label="Highlights" className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm text-text-secondary">
              {["PDF summaries", "Figure insights", "Custom templates"].map((t) => (
                <li key={t} className="inline-flex items-center gap-1.5"><Check aria-hidden className="size-4 text-text" />{t}</li>
              ))}
            </ul>
          </div>
          <div className="relative mx-auto mt-12 max-w-6xl md:mt-16">
            <ProductShot />
          </div>
        </section>

        <Section id="how" title="How it works" intro="From PDF to answers you can check, in three steps.">
          <ol className="grid gap-6 md:grid-cols-3">
            {STEPS.map(({ n, title, text, Icon }) => (
              <li key={n} className="flex items-start gap-4">
                <span className="inline-flex size-14 shrink-0 items-center justify-center rounded-lg border border-border bg-surface shadow-card">
                  <Icon aria-hidden className="size-6" />
                </span>
                <div>
                  <h3 className="font-display text-xl font-bold">{`${String(n)}. ${title}`}</h3>
                  <p className="mt-1 text-text-secondary">{text}</p>
                </div>
              </li>
            ))}
          </ol>
          <DemoVideo />
        </Section>

        <Section id="features" title="Everything a paper needs" intro="Built for researchers who want to understand, not skim.">
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map(({ title, text, Icon }) => (
              <li key={title} className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-6">
                <span className="inline-flex size-11 items-center justify-center rounded-md bg-muted">
                  <Icon aria-hidden className="size-5" />
                </span>
                <h3 className="font-display text-xl font-bold">{title}</h3>
                <p className="text-text-secondary">{text}</p>
              </li>
            ))}
          </ul>
        </Section>

        <Section id="plans" title="Free during preview" intro="Everything you need to read papers well, at no cost while Abstract is in preview.">
          <div className="mx-auto flex w-full max-w-md flex-col gap-5 rounded-xl border border-border bg-surface p-6 shadow-card md:p-8">
            <div>
              <p className="font-display text-2xl font-bold">Free</p>
              <p className="text-text-secondary">No card needed.</p>
            </div>
            <ul aria-label="Included in Free" className="flex flex-col gap-2">
              {FREE.map((f) => (
                <li key={f} className="flex items-start gap-2"><Check aria-hidden className="mt-0.5 size-5 shrink-0" />{f}</li>
              ))}
            </ul>
            <a href={signedIn ? APP : SIGN_UP} className={primary}>{signedIn ? "Open your library" : "Get started free"}</a>
            <p className="text-center text-sm text-text-secondary">Pro, with higher limits, is coming soon.</p>
          </div>
        </Section>

        <section aria-labelledby="cta-title" className="px-4 pb-20 md:px-8">
          <div className="mx-auto flex max-w-6xl flex-col items-center gap-5 rounded-xl bg-primary px-6 py-14 text-center text-primary-text">
            <h2 id="cta-title" className="font-display text-3xl font-bold tracking-tight md:text-4xl">Read your next paper with Abstract.</h2>
            <a href={signedIn ? APP : SIGN_UP} className="inline-flex min-h-11 items-center gap-2 rounded-pill bg-surface px-6 font-medium text-text hover:opacity-90">
              {signedIn ? "Open your library" : "Get started"}
              <ArrowRight aria-hidden className="size-5" />
            </a>
          </div>
        </section>
      </main>

      <footer className="border-t border-border px-4 py-8 md:px-8">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 text-sm text-text-secondary">
          <span className="inline-flex items-center gap-2"><LogoMark className="size-6" />{`© ${String(new Date().getFullYear())} Abstract.`}</span>
        </div>
      </footer>
    </div>
  );
}
