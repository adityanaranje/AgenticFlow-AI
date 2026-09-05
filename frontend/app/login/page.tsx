"use client";

import { useState, type SubmitEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { createClient } from "@/lib/supabase/client";
import { UserSearch } from "lucide-react";

export default function LoginPage() {
    const router = useRouter();
    const searchParams = useSearchParams();

    const redirect = searchParams.get("redirect") || "/dashboard";

    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
 
    async function  handleLogin(evennt: SubmitEvent<HTMLFormElement>,
    ) {
        event?.preventDefault()

        setLoading(true);
        setError(null);

        const supabase = createClient();

        const {
            error : loginError,
        } = await supabase.auth.signInWithPassword({
            email,
            password,
        });

        if(loginError){
            setError(loginError.message);
            setLoading(false);
            return;
        }

        router.replace(
            redirect.startsWith("/")
            ? redirect
            : "/dashboard",
        );

        router.refresh();
    }

    return (
        <main 
        style={{
            minHeight: "100vh",
            display:"grid",
            placeItems:"center",
            padding:"24px",
        }}
        >
            <div
            style={{
                width:"100%",
                maxWidth:"420px",
            }}>
                <h1>Sign in</h1>
                <p>Sign in to AgentFlow AI</p>
                <form
                onSubmit={handleLogin}
                style={{
                    display:"grid",
                    gap:"16px",
                    marginTop:"24px",
                }}>

                    <label>
                        Email
                    <input 
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(
                        event.target.value,
                    )}
                    required
                    autoComplete="email"
                    style={{
                        display:"block",
                        width:"100%",
                        marginTop:"6px",
                        padding:"10px",
                    }}
                    />
                    </label>
                    
                    <label>
                    Password
                    <input
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(
                        event.target.value,
                    )}
                required
                autoComplete="current-password"
                style={{
                    display:"block",
                    width:"100%",
                    marginTop:"6px",
                    padding:"10px",
                }}
                    />
  
                    </label>


                    {error && (
                        <p
                        role="alert"
                        style={{
                            color: "crimson",
                        }}>
                            {error}
                        </p>
                    )}

                    <button
                    type="submit"
                    disabled={loading}>
                        {loading ? "Signing in...." : "Sign in"}
                    </button>
                </form>
                <p
                style={{
                    marginTop:"20px",
                }}>
                    Don't have an account?{" "}
                    <a href="/signup">
                    Create one
                    </a>
                </p>
            </div>
        </main>
    );
}