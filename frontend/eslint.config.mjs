import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // App code only: Node scripts (scripts/*.mjs) legitimately index
    // process.env, since nothing there is bundled for the browser.
    files: ["app/**/*", "components/**/*", "lib/**/*"],
    rules: {
      /*
       * Guard against the classic Next.js env footgun: only *static* member
       * expressions (`process.env.NEXT_PUBLIC_X`) are replaced with their
       * values when the browser bundle is built. `process.env[name]` stays a
       * runtime lookup and reads as `undefined` in the client — which is how a
       * correctly configured .env.local can still produce "Missing
       * NEXT_PUBLIC_SUPABASE_URL" in the browser. Read the literal once and
       * snapshot it (see the PUBLIC_ENV map in lib/env.ts).
       */
      "no-restricted-syntax": [
        "error",
        {
          selector:
            'MemberExpression[computed=true][object.object.name="process"][object.property.name="env"]',
          message:
            "Dynamic process.env[...] reads are not inlined into the browser bundle and are undefined on the client. Use a static expression (process.env.NEXT_PUBLIC_SOMETHING) — snapshot it in lib/env.ts if you need to look values up by name.",
        },
      ],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
