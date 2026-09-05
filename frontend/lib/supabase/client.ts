import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

    if(!supabaseUrl){
        throw new Error("Missing NEXT_PUBLIC_SUPABASE_URL");
    }

    if(!supabaseAnonKey){
        throw new Error("Missing NEXT_PUBLIC_SUPABASE_ANON_KEY");
    }

    return createBrowserClient(
        supabaseUrl,
        supabaseAnonKey,
    );
}