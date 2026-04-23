import { auth } from "@/lib/firebase";
import type { QueryRequest, QueryResponse, StreamEvent } from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

/** Obtiene el encabezado Authorization si hay sesión activa. */
async function getAuthHeaders(): Promise<Record<string, string>> {
  const user = auth.currentUser;
  if (!user) return {};
  const token = await user.getIdToken(/* forceRefresh */ true);
  return { Authorization: `Bearer ${token}` };
}

export async function queryRag(
  request: QueryRequest
): Promise<QueryResponse> {
  const authHeaders = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(
      detail.trim() || `Error del servidor (${res.status})`
    );
  }

  return res.json() as Promise<QueryResponse>;
}

/**
 * Async generator que conecta al endpoint SSE de streaming y emite eventos
 * tipados a medida que llegan.
 *
 * Uso:
 *   for await (const event of queryRagStream({ question: "..." })) {
 *     if (event.type === "token") { ... }
 *     else if (event.type === "sources") { ... }
 *   }
 */
export async function* queryRagStream(
  request: QueryRequest
): AsyncGenerator<StreamEvent> {
  const authHeaders = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders },
    body: JSON.stringify(request),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(
      detail.trim() || `Error del servidor (${res.status})`
    );
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Los eventos SSE están separados por doble salto de línea
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data: ")) continue;

        const data = line.slice(6);
        if (data === "[DONE]") return;

        yield JSON.parse(data) as StreamEvent;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
