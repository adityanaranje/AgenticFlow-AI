import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export default async function DashboardPage() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const { data: profile } = await supabase
    .from("profiles")
    .select("id, full_name, avatar_url")
    .eq("id", user.id)
    .maybeSingle();

  const { data: memberships } = await supabase
    .from("organization_members")
    .select(
      `
        organization_id,
        role,
        organizations (
          id,
          name,
          slug
        )
      `
    )
    .eq("user_id", user.id);

  return (
    <main
      style={{
        maxWidth: "1000px",
        margin: "0 auto",
        padding: "40px 24px",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "20px",
        }}
      >
        <div>
          <h1>
            Welcome{profile?.full_name ? `, ${profile.full_name}` : ""}
          </h1>
          <p>{user.email}</p>
        </div>

        <form action="/auth/logout" method="POST">
          <button type="submit">Sign out</button>
        </form>
      </div>

      <section style={{ marginTop: "40px" }}>
        <h2>Your organizations</h2>

        {!memberships || memberships.length === 0 ? (
          <p>You are not a member of any organization yet.</p>
        ) : (
          <div
            style={{
              display: "grid",
              gap: "16px",
              marginTop: "20px",
            }}
          >
            {memberships.map((membership) => {
              // Supabase returns the foreign object directly (or null/array depending on FK definitions)
              // Normalizing it handles single objects safely:
              const organization = Array.isArray(membership.organizations)
                ? membership.organizations[0]
                : membership.organizations;

              if (!organization) {
                return null;
              }

              return (
                <div
                  key={membership.organization_id}
                  style={{
                    border: "1px solid #ddd",
                    borderRadius: "8px",
                    padding: "20px",
                  }}
                >
                  <h3>{organization.name}</h3>
                  <p>Slug: {organization.slug}</p>
                  <p>Role: {membership.role}</p>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}