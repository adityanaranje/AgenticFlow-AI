import { createServerClient } from "@supabase/ssr";
import { error } from "console";
import { cookies } from "next/headers";

export async function createClient() {
  const cookieStore = await cookies();

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl) {
    throw new Error("Missing NEXT_PUBLIC_SUPABASE_URL");
  }

  if (!supabaseAnonKey) {
    throw new Error("Missing NEXT_PUBLIC_SUPABASE_ANON_KEY");
  }

  return createServerClient(
    supabaseUrl,
    supabaseAnonKey,
    {
        cookies: {
            getAll() {
                return cookieStore.getAll();
            },

            setAll(cookiesToSet){
                try{
                    cookiesToSet.forEach(
                        ({
                            name,
                            value,
                            options,
                        }) => {
                            cookieStore.set(
                                name,
                                value,
                                options,
                            );
                        },
                    );
                } catch {
                    // cookie writes can fail when call
                    // from a server component.
                }
            },
        },
    },
  );
}
