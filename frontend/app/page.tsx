import Link from "next/link";
import {
  ArrowRight,
  Bot,
  ClipboardCheck,
  FileSearch,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";

import Logo from "@/components/brand/Logo";

const features = [
  {
    icon: UploadCloud,
    title: "Knowledge base",
    text: "Upload documents and let the platform chunk, embed and index them into a searchable knowledge base.",
  },
  {
    icon: Bot,
    title: "Agentic research",
    text: "LangGraph agents plan, research, verify and refine answers grounded in your organization's data.",
  },
  {
    icon: FileSearch,
    title: "Cited reports",
    text: "Generate structured reports with citations you can trace back to the source documents.",
  },
  {
    icon: ClipboardCheck,
    title: "Quality evaluation",
    text: "Continuously score the quality of generated answers to keep research trustworthy.",
  },
];

/**
 * Home page — public landing / application shell entry point.
 *
 * Phase 1 scope: no AI functionality is claimed or faked here.
 * The page describes the platform and links to authentication,
 * which is handled by Supabase Auth (email + Google).
 */
export default function Home() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-zinc-50 dark:bg-zinc-950">
      {/* Decorative glows */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute left-1/2 top-[-20%] h-[560px] w-[900px] -translate-x-1/2 rounded-full bg-gradient-to-br from-indigo-400/25 via-violet-400/15 to-fuchsia-400/20 blur-3xl dark:from-indigo-600/20 dark:via-violet-600/10 dark:to-fuchsia-600/15" />
        <div
          className="absolute inset-0 opacity-[0.4] dark:opacity-[0.25]"
          style={{
            backgroundImage:
              "radial-gradient(circle at 1px 1px, rgb(161 161 170 / 0.35) 1px, transparent 0)",
            backgroundSize: "36px 36px",
            maskImage:
              "radial-gradient(ellipse 70% 55% at 50% 0%, black 55%, transparent 100%)",
            WebkitMaskImage:
              "radial-gradient(ellipse 70% 55% at 50% 0%, black 55%, transparent 100%)",
          }}
        />
      </div>

      {/* Nav */}
      <header className="relative z-10 mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6">
        <Link href="/" aria-label="AgentFlow AI home">
          <Logo />
        </Link>

        <nav className="flex items-center gap-2" aria-label="Account">
          <Link
            href="/login"
            className="btn-secondary px-5"
          >
            Sign in
          </Link>
          <Link
            href="/signup"
            className="btn-primary px-5"
          >
            Get started
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </nav>
      </header>

      <main className="relative z-10 mx-auto w-full max-w-6xl px-6">
        {/* Hero */}
        <section className="flex flex-col items-center py-20 text-center sm:py-28">
          <span className="animate-fade-up inline-flex items-center gap-2 rounded-full border border-indigo-200/70 bg-white/70 px-4 py-1.5 text-xs font-medium text-indigo-700 shadow-sm backdrop-blur dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-indigo-300">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-2 w-2 animate-ping rounded-full bg-indigo-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-indigo-500" />
            </span>
            Phase 1 · Foundation &amp; infrastructure
          </span>

          <h1 className="animate-fade-up anim-delay-1 mt-7 max-w-3xl text-4xl font-semibold leading-[1.1] tracking-tight text-zinc-950 dark:text-white sm:text-6xl">
            Research your organization&apos;s knowledge{" "}
            <span className="bg-gradient-to-r from-indigo-600 via-violet-600 to-fuchsia-600 bg-clip-text text-transparent dark:from-indigo-400 dark:via-violet-400 dark:to-fuchsia-400">
              with AI agents
            </span>
          </h1>

          <p className="animate-fade-up anim-delay-2 mt-6 max-w-2xl text-lg leading-relaxed text-zinc-600 dark:text-zinc-400">
            AgentFlow AI turns your documents into a searchable knowledge base,
            runs agentic research workflows, generates cited reports and
            evaluates the quality of every answer.
          </p>

          <div className="animate-fade-up anim-delay-3 mt-10 flex w-full flex-col items-center justify-center gap-3 sm:w-auto sm:flex-row">
            <Link
              href="/signup"
              className="btn-primary w-full px-8 sm:w-auto"
            >
              Create your account
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
            <Link href="/login" className="btn-secondary w-full px-8 sm:w-auto">
              Sign in
            </Link>
          </div>

          <p className="animate-fade-up anim-delay-4 mt-5 flex items-center gap-1.5 text-xs text-zinc-400 dark:text-zinc-500">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" aria-hidden="true" />
            Multi-tenant by design — your data stays inside your organization.
          </p>
        </section>

        {/* Features */}
        <section className="pb-24">
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {features.map(({ icon: Icon, title, text }, index) => (
              <article
                key={title}
                className="card animate-fade-up p-7 transition duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-indigo-500/10"
                style={{ animationDelay: `${index * 90}ms` }}
              >
                <span className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500/15 to-violet-500/15 text-indigo-600 ring-1 ring-indigo-500/20 dark:text-indigo-400">
                  <Icon className="h-5 w-5" aria-hidden="true" />
                </span>
                <h2 className="mt-5 text-base font-semibold text-zinc-900 dark:text-white">
                  {title}
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-zinc-500 dark:text-zinc-400">
                  {text}
                </p>
              </article>
            ))}
          </div>
        </section>
      </main>

      <footer className="relative z-10 border-t border-zinc-200/70 py-8 dark:border-zinc-800/70">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 text-xs text-zinc-400 dark:text-zinc-500 sm:flex-row">
          <p>© {new Date().getFullYear()} AgentFlow AI</p>
          <p>Backend · FastAPI — Frontend · Next.js — Vectors · Qdrant — Observability · Langfuse</p>
        </div>
      </footer>
    </div>
  );
}
