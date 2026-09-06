import Link from "next/link";

/**
 * Home page - public landing / application shell entry point.
 *
 * Phase 1 scope: no AI functionality is claimed or faked here.
 * The page describes the platform and links to authentication,
 * which is handled by Supabase Auth.
 */
export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center px-6 py-24">
      <section className="w-full max-w-2xl text-center">
        <p className="text-sm font-medium uppercase tracking-widest text-zinc-500 dark:text-zinc-400">
          AgentFlow AI
        </p>
        <h1 className="mt-4 text-4xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50 sm:text-5xl">
          AI research platform for your organization&apos;s knowledge
        </h1>
        <p className="mx-auto mt-6 max-w-xl text-lg leading-8 text-zinc-600 dark:text-zinc-400">
          Upload documents, build a searchable knowledge base, run
          AI-powered research, generate reports and evaluate the
          quality of generated answers.
        </p>

        <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href="/login"
            className="inline-flex h-12 w-full items-center justify-center rounded-full bg-zinc-900 px-8 text-base font-medium text-white transition-colors hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300 sm:w-auto"
          >
            Sign in
          </Link>
          <Link
            href="/signup"
            className="inline-flex h-12 w-full items-center justify-center rounded-full border border-zinc-300 px-8 text-base font-medium text-zinc-900 transition-colors hover:border-zinc-900 dark:border-zinc-700 dark:text-zinc-100 dark:hover:border-zinc-300 sm:w-auto"
          >
            Create an account
          </Link>
        </div>
      </section>

      <footer className="mt-20 text-sm text-zinc-400 dark:text-zinc-600">
        Phase 1 — project foundation &amp; infrastructure
      </footer>
    </main>
  );
}
