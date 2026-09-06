import type { ReactNode } from "react";
import { Bot, FileSearch, UploadCloud } from "lucide-react";

import Logo from "@/components/brand/Logo";

const valueProps = [
  {
    icon: UploadCloud,
    title: "Upload documents",
    text: "Build a searchable knowledge base for your organization.",
  },
  {
    icon: Bot,
    title: "Agentic research",
    text: "LangGraph agents plan, research and verify with citations.",
  },
  {
    icon: FileSearch,
    title: "Reports & evaluation",
    text: "Generate reports and measure the quality of every answer.",
  },
];

/**
 * Split-screen shell shared by the login and sign-up pages:
 * a brand panel on the left, the auth card on the right.
 */
export default function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="relative flex min-h-screen w-full items-stretch bg-zinc-50 dark:bg-zinc-950">
      {/* Decorative page glows */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-32 right-[-10%] h-96 w-96 rounded-full bg-indigo-400/20 blur-3xl animate-pulse-glow dark:bg-indigo-500/10" />
        <div className="absolute bottom-[-15%] left-[-5%] h-96 w-96 rounded-full bg-violet-400/15 blur-3xl dark:bg-violet-500/10" />
      </div>

      {/* Brand panel */}
      <aside className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-zinc-950 p-12 lg:flex xl:p-16">
        {/* Ambient orbs */}
        <div aria-hidden="true" className="absolute inset-0">
          <div className="animate-float-slow absolute -left-24 top-10 h-80 w-80 rounded-full bg-indigo-600/30 blur-3xl" />
          <div
            className="animate-float-slow absolute -right-16 bottom-24 h-96 w-96 rounded-full bg-violet-600/25 blur-3xl"
            style={{ animationDelay: "-7s" }}
          />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(9,9,11,0.55)_100%)]" />
        </div>

        <div className="relative flex flex-col gap-16">
          <Logo dark />

          <div className="max-w-md space-y-6">
            <h1 className="text-4xl font-semibold leading-tight tracking-tight text-white xl:text-[2.75rem] xl:leading-[1.15]">
              Your organization&apos;s knowledge,{" "}
              <span className="bg-gradient-to-r from-indigo-300 via-violet-300 to-fuchsia-300 bg-clip-text text-transparent">
                researched by AI agents
              </span>
            </h1>

            <ul className="space-y-5">
              {valueProps.map(({ icon: Icon, title: itemTitle, text }) => (
                <li key={itemTitle} className="flex items-start gap-4">
                  <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-indigo-200 backdrop-blur">
                    <Icon className="h-5 w-5" aria-hidden="true" />
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-white">{itemTitle}</p>
                    <p className="mt-0.5 text-sm leading-relaxed text-zinc-400">{text}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <p className="relative text-xs text-zinc-500">
          AgentFlow AI — Phase 1 · Foundation &amp; infrastructure
        </p>
      </aside>

      {/* Form panel */}
      <section className="relative flex w-full flex-col items-center justify-center px-6 py-12 lg:w-1/2">
        <div className="w-full max-w-md animate-fade-up">
          <div className="mb-8 flex items-center justify-center lg:hidden">
            <Logo />
          </div>

          <div className="rounded-3xl border border-zinc-200/80 bg-white p-8 shadow-xl shadow-zinc-900/5 dark:border-zinc-800 dark:bg-zinc-900 dark:shadow-black/30 sm:p-10">
            <h2 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-white">
              {title}
            </h2>
            <p className="mt-1.5 text-sm text-zinc-500 dark:text-zinc-400">{subtitle}</p>

            <div className="mt-7">{children}</div>
          </div>

          {footer && (
            <p className="mt-6 text-center text-sm text-zinc-500 dark:text-zinc-400">
              {footer}
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
