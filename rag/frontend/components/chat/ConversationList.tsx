"use client";

import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
} from "react";
import { AnimatePresence, motion } from "motion/react";
import { expireAuthSession, getToken } from "@/lib/auth";
import { readErrorDetail, throwIfSessionExpired } from "@/lib/api";
import type { Conversation } from "@/hooks/useConversations";
import { formatConversationDate } from "@/components/chat/conversationSidebarUtils";
import { API_URL } from "@/lib/config";

// A2 — el backend acepta hasta 120 caracteres para el título de una
// conversación (`UpdateConversationRequest.title`, `max_length=120`); antes
// el campo truncaba en silencio a 60 sin que esa cifra correspondiera a
// ningún límite real del contrato.
const MAX_TITLE_CHARS = 120;

interface ConversationListProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  loading: boolean;
  /**
   * A4 — mensaje del último intento fallido de refrescar el listado (ver
   * `useConversations`). La lista de `conversations` recibida sigue siendo
   * la última válida conocida incluso cuando este campo no es null: el
   * fallo se muestra como un aviso, nunca como una lista vaciada.
   */
  loadError?: string | null;
  /** Reintenta el refresco tras `loadError`. Requerido si se pasa `loadError`. */
  onRetryLoad?: () => Promise<void>;
  onSelectConversation: (conv: Conversation) => Promise<void>;
  onNewChat: () => void;
  onConversationsRefresh?: () => Promise<void>;
}

export function ConversationList({
  conversations,
  activeConversationId,
  loading,
  loadError = null,
  onRetryLoad,
  onSelectConversation,
  onNewChat,
  onConversationsRefresh,
}: ConversationListProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editError, setEditError] = useState<string | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletingInFlight, setDeletingInFlight] = useState(false);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const editInputRef = useRef<HTMLInputElement>(null);
  // A2.5 — guardas síncronas contra doble envío por Enter+blur (o doble
  // clic en "Eliminar"): se fijan ANTES del primer `await`, así que un
  // segundo disparo que llegue mientras el primero sigue en vuelo se corta
  // de inmediato, sin depender del re-render de los estados `saving*`.
  const savingEditRef = useRef(false);
  const deletingInFlightRef = useRef(false);

  useEffect(() => {
    if (editingId) editInputRef.current?.focus();
  }, [editingId]);

  useEffect(() => {
    if (!menuOpenId) return;

    const closeMenu = (event: globalThis.MouseEvent) => {
      const target = event.target as Element;
      if (target.closest("[data-conversation-menu-root]")) return;
      setMenuOpenId(null);
    };

    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpenId(null);
    };

    document.addEventListener("mousedown", closeMenu);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeMenu);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [menuOpenId]);

  function startEdit(conv: Conversation, event: MouseEvent) {
    event.stopPropagation();
    setMenuOpenId(null);
    setDeletingId(null);
    setDeleteError(null);
    setEditingId(conv.id);
    setEditTitle(conv.title ?? "");
    setEditError(null);
  }

  async function saveEdit(convId: string) {
    if (savingEditRef.current) return;

    const original = conversations.find((c) => c.id === convId)?.title ?? "";
    const title = editTitle.trim();

    // A2.9 — título vacío: mantener la edición abierta con un mensaje de
    // validación, nunca cerrarla ni enviar la solicitud.
    if (!title) {
      setEditError("El título no puede estar vacío.");
      return;
    }
    if (title.length > MAX_TITLE_CHARS) {
      setEditError(
        `El título no puede superar ${MAX_TITLE_CHARS} caracteres.`,
      );
      return;
    }
    // A2.8 — sin cambios: cerrar la edición sin hacer ninguna solicitud.
    if (title === original) {
      setEditingId(null);
      setEditError(null);
      return;
    }

    const token = getToken();
    if (!token) {
      // Este componente solo se renderiza autenticado: si el token ya no
      // está, notifica para que la UI se actualice en vez de descartar la
      // edición en silencio.
      expireAuthSession(null);
      return;
    }

    savingEditRef.current = true;
    setSavingEdit(true);
    setEditError(null);
    try {
      const res = await fetch(`${API_URL}/api/conversations/${convId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ title }),
      });
      await throwIfSessionExpired(res, token);
      // A2.1 — comprobar siempre res.ok después de tratar el 401: un
      // fallo real (4xx/5xx) ya no se trataba como éxito silencioso.
      if (!res.ok) {
        setEditError(await readErrorDetail(res));
        return;
      }
      // A2.3 — la edición solo se cierra cuando el renombrado fue
      // confirmado por el backend.
      setEditingId(null);
      setEditError(null);
      // A2.7 — refrescar la lista únicamente tras un éxito confirmado.
      await onConversationsRefresh?.();
    } catch (error) {
      // A2.2 — error local comprensible, sin vaciar el historial: la
      // edición se mantiene abierta para que el usuario pueda reintentar
      // o cancelar con Escape.
      setEditError(
        error instanceof Error
          ? error.message
          : "No fue posible renombrar la conversación.",
      );
    } finally {
      savingEditRef.current = false;
      setSavingEdit(false);
    }
  }

  function handleEditKeyDown(event: KeyboardEvent, convId: string) {
    if (event.key === "Enter") saveEdit(convId);
    if (event.key === "Escape") {
      setEditingId(null);
      setEditError(null);
    }
  }

  function requestDelete(convId: string, event: MouseEvent) {
    event.stopPropagation();
    setMenuOpenId(null);
    setEditingId(null);
    setEditError(null);
    setDeletingId(convId);
    setDeleteError(null);
  }

  async function confirmDelete(convId: string, event: MouseEvent) {
    event.stopPropagation();
    if (deletingInFlightRef.current) return;

    const token = getToken();
    if (!token) {
      // Igual que en saveEdit: notifica si el token ya no está.
      expireAuthSession(null);
      return;
    }

    deletingInFlightRef.current = true;
    setDeletingInFlight(true);
    setDeleteError(null);
    try {
      const res = await fetch(`${API_URL}/api/conversations/${convId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      await throwIfSessionExpired(res, token);
      // A2.1 — mismo chequeo explícito de res.ok que en saveEdit.
      if (!res.ok) {
        setDeleteError(await readErrorDetail(res));
        return;
      }
      setDeletingId(null);
      setDeleteError(null);
      // A2.7 — refrescar solo tras éxito confirmado.
      await onConversationsRefresh?.();
      // A2.4 — onNewChat() solo se dispara después de eliminar con éxito
      // la conversación que estaba activa, nunca antes ni ante un fallo.
      if (convId === activeConversationId) onNewChat();
    } catch (error) {
      setDeleteError(
        error instanceof Error
          ? error.message
          : "No fue posible eliminar la conversación.",
      );
    } finally {
      deletingInFlightRef.current = false;
      setDeletingInFlight(false);
    }
  }

  function cancelDelete(event: MouseEvent) {
    event.stopPropagation();
    setDeletingId(null);
    setDeleteError(null);
  }

  if (loading && conversations.length === 0) {
    return <p className="px-5 py-4 text-xs text-subtle">Cargando…</p>;
  }

  // A4 — un fallo de carga con la lista todavía vacía (nunca hubo una lista
  // válida que conservar) se muestra como error explícito con reintento, en
  // vez de la copia genérica "aún no tienes conversaciones" (que sería
  // engañosa: el usuario sí podría tener conversaciones, solo que no se
  // pudieron cargar).
  if (!loading && loadError && conversations.length === 0) {
    return (
      <div className="px-5 py-4">
        <p role="alert" className="text-xs text-danger">
          {loadError}
        </p>
        {onRetryLoad && (
          <button
            type="button"
            onClick={() => onRetryLoad()}
            className="mt-1.5 text-xs font-medium text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            Reintentar
          </button>
        )}
      </div>
    );
  }

  if (!loading && conversations.length === 0) {
    return (
      <p className="px-5 py-4 text-xs text-subtle">
        Tus conversaciones aparecerán aquí.
      </p>
    );
  }

  return (
    <>
      {/* A4 — fallo de refresco con una lista previa aún válida: se conserva
          la lista en pantalla y el aviso se muestra aparte, sin bloquear ni
          vaciar nada. */}
      {loadError && (
        <div className="flex items-center justify-between gap-2 px-5 py-2">
          <p role="alert" className="truncate text-[11px] text-danger">
            {loadError}
          </p>
          {onRetryLoad && (
            <button
              type="button"
              onClick={() => onRetryLoad()}
              className="shrink-0 text-[11px] font-medium text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              Reintentar
            </button>
          )}
        </div>
      )}
      <ul className="px-2 pb-2">
      {conversations.map((conv) => {
        const isActive = conv.id === activeConversationId;
        const isDeleting = deletingId === conv.id;
        const isEditing = editingId === conv.id;

        return (
          <li
            key={conv.id}
            className={`group relative my-px flex items-center rounded-full pl-3 pr-1 text-[13px] transition-colors ${
              isActive
                ? "bg-elevated text-foreground"
                : "text-muted hover:bg-elevated hover:text-foreground"
            }`}
            aria-current={isActive ? "true" : undefined}
          >
            <div className="min-w-0 flex-1 py-2">
              {isEditing ? (
                <div className="min-w-0">
                  <input
                    ref={editInputRef}
                    value={editTitle}
                    onChange={(event) => setEditTitle(event.target.value)}
                    onBlur={() => saveEdit(conv.id)}
                    onKeyDown={(event) => handleEditKeyDown(event, conv.id)}
                    maxLength={MAX_TITLE_CHARS}
                    disabled={savingEdit}
                    aria-invalid={editError ? "true" : undefined}
                    className="w-full rounded-md border border-accent bg-background px-1.5 py-0.5 text-[13px] text-foreground focus:outline-none disabled:opacity-60"
                    onClick={(event) => event.stopPropagation()}
                  />
                  {editError && (
                    <p role="alert" className="mt-0.5 truncate text-[10px] text-danger">
                      {editError}
                    </p>
                  )}
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => onSelectConversation(conv)}
                  title={`${conv.title ?? "Sin título"} · ${formatConversationDate(conv.updatedAt)}`}
                  className="block w-full min-w-0 cursor-pointer truncate text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  {conv.title ?? "Sin título"}
                </button>
              )}
            </div>

            {!isEditing && !isDeleting && (
              <ConversationActionsMenu
                conversation={conv}
                isOpen={menuOpenId === conv.id}
                onToggle={() =>
                  setMenuOpenId((current) =>
                    current === conv.id ? null : conv.id
                  )
                }
                onRename={startEdit}
                onDelete={requestDelete}
              />
            )}

            {isDeleting && (
              <div className="absolute inset-x-2 top-full z-10 mt-1">
                <DeleteConfirmation
                  error={deleteError}
                  inFlight={deletingInFlight}
                  onConfirm={(event) => confirmDelete(conv.id, event)}
                  onCancel={cancelDelete}
                />
              </div>
            )}
          </li>
        );
      })}
      </ul>
    </>
  );
}

function ConversationActionsMenu({
  conversation,
  isOpen,
  onToggle,
  onRename,
  onDelete,
}: {
  conversation: Conversation;
  isOpen: boolean;
  onToggle: () => void;
  onRename: (conv: Conversation, event: MouseEvent) => void;
  onDelete: (convId: string, event: MouseEvent) => void;
}) {
  return (
    <div className="relative shrink-0" data-conversation-menu-root>
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          onToggle();
        }}
        aria-label={`Opciones para ${conversation.title ?? "conversación"}`}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        className="flex h-7 w-7 items-center justify-center rounded-full text-muted opacity-0 transition-[background-color,color,opacity] duration-150 hover:bg-surface hover:text-foreground focus:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent group-hover:opacity-100 group-focus-within:opacity-100"
      >
        <DotsIcon />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            role="menu"
            className="absolute right-0 top-8 z-50 w-40 rounded-xl border border-border bg-elevated p-1 shadow-lg shadow-secondary-turquoise/15"
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              role="menuitem"
              onClick={(event) => onRename(conversation, event)}
              className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs text-muted transition-colors hover:bg-accent/8 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              <EditIcon />
              Renombrar
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={(event) => onDelete(conversation.id, event)}
              className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs text-danger transition-colors hover:bg-danger-bg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger"
            >
              <TrashIcon />
              Eliminar
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function DeleteConfirmation({
  error,
  inFlight,
  onConfirm,
  onCancel,
}: {
  error: string | null;
  inFlight: boolean;
  onConfirm: (event: MouseEvent) => void;
  onCancel: (event: MouseEvent) => void;
}) {
  return (
    <div
      className="mt-2 rounded-lg border border-danger/30 bg-danger-bg px-2.5 py-2"
      onClick={(event) => event.stopPropagation()}
    >
      <p className="text-[10px] font-medium text-danger">
        ¿Eliminar esta conversación?
      </p>
      {error && (
        <p role="alert" className="mt-1 text-[10px] text-danger">
          {error}
        </p>
      )}
      <div className="mt-1.5 flex items-center gap-1.5">
        <button
          onClick={onConfirm}
          disabled={inFlight}
          className="rounded-md bg-danger px-2 py-1 text-[10px] font-medium text-surface transition-colors hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {inFlight ? "Eliminando…" : "Eliminar"}
        </button>
        <button
          onClick={onCancel}
          disabled={inFlight}
          className="rounded-md px-2 py-1 text-[10px] text-muted transition-colors hover:bg-surface hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-60"
        >
          Cancelar
        </button>
      </div>
    </div>
  );
}

function DotsIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="1" />
      <circle cx="19" cy="12" r="1" />
      <circle cx="5" cy="12" r="1" />
    </svg>
  );
}

function EditIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  );
}
