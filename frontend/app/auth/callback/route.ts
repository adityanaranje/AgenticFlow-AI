import { NextResponse } from "next/server";

import { createClient } from "@/lib/supabase/server";

export async function GET(
    request: Request,
) {
    const { searchParams} = 
    new URL(request.url);

    const code = searchParams.get("code");

    const redirectTo = searchParams.get("redirect") || "/dashboard";

    if (!code) {
        return NextResponse.redirect(
            new URL(
                "/login?error=missing_code",
                request.url,           
            ),
        );
    }

    const supabase = await createClient();

    const {
        error,
    } = await supabase.auth.exchangeCodeForSession(
        code,
    );

    if( error) {
        return NextResponse.redirect(
            new URL(
                `/login?error=${encodeURIComponent(
                    error.message,
                )}`,
                request.url,
            ),
        );
    }

    return NextResponse.redirect(
        new URL(
            redirectTo.startsWith("/")
            ? redirectTo
            : "/dashboard",
            request.url,
        ),
    );
}