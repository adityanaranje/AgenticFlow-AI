/**
 * Centralized API client for the AgentFlow AI FastAPI backend.
 *
 * All HTTP calls to the backend must go through this module —
 * do not scatter raw `fetch` calls across the application.
 * The client targets the versioned base URL (NEXT_PUBLIC_API_URL
 * + `/api/v1`) and normalizes errors into ApiError instances.
 */

import { API_BASE_URL } from "@/lib/env";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;

  constructor(status: number, message: string, detail: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}

const isFormData = (body: unknown): body is FormData =>
  typeof FormData !== "undefined" && body instanceof FormData;

/**
 * The FastAPI backend authenticates with the caller's Supabase session
 * (``Authorization: Bearer <access_token>``). In the browser we attach the
 * signed-in user's token so backend endpoints can authorize the request.
 */
async function resolveAuthHeaders(): Promise<Record<string, string>> {
  if (typeof window === "undefined") return {};
  try {
    const { createClient } = await import("@/lib/supabase/client");
    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    const token = session?.access_token;
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, headers, ...init } = options;

  const url = `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;

  const authHeaders = await resolveAuthHeaders();

  const response = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      // FormData sets its own multipart Content-Type boundary.
      ...(body !== undefined && !isFormData(body)
        ? { "Content-Type": "application/json" }
        : {}),
      ...authHeaders,
      ...headers,
    },
    body: isFormData(body) ? (body as unknown as BodyInit) : body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });

  if (!response.ok) {
    let detail: string | null = null;
    let message = `Request failed with status ${response.status}`;

    try {
      const payload = await response.json();

      if (typeof payload?.detail === "string") {
        detail = payload.detail;
        message = payload.detail;
      }
    } catch {
      // Non-JSON error body; keep the generic message.
    }

    throw new ApiError(response.status, message, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const apiClient = {
  get<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: "GET" });
  },

  post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: "POST", body });
  },

  put<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: "PUT", body });
  },

  patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: "PATCH", body });
  },

  delete<T>(path: string, options?: RequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: "DELETE" });
  },
};

export default apiClient;
