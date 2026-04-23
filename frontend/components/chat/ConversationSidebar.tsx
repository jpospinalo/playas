"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { collection, deleteDoc, doc, getDocs, updateDoc, writeBatch } from "firebase/firestore";
import { db } from "@/lib/firebase";
import type { Conversation } from "@/hooks/useConversations";

interface ConversationSidebarProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  loading: boolean;
  onSelectConversation: (conv: Conversation) => Promise<void>;
  onNewChat: () => void;
  onClose: () => void;
}

export function ConversationSidebar({
  conversations,
  activeConversationId,
  loading,
  onSelectConversation,
  onNewChat,
  onClose,
}: ConversationSidebarProps) {
  const [search, setSearch] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const editInputRef = useRef<HTMLInputElement>(null);

  const filtered = conversations.filter((c) =>
    c.title.toLowerCase().includes(search.toLowerCase())
  );

  useEffect(() => {
    if (editingId) editInputRef.current?.focus();
  }, [editingId]);

  function startEdit(conv: Conversation, e: React.MouseEvent) {
    e.stopPropagation();
    setEditingId(conv.id);
    setEditTitle(conv.title);
  }

  async function saveEdit(convId: string) {
    const title = editTitle.trim().slice(0, 60);
    if (title) {
      await updateDoc(doc(db, "conversations", convId), { title }).catch(
        () => {}
      );
    }
    setEditingId(null);
  }

  function handleEditKeyDown(e: React.KeyboardEvent, convId: string) {
    if (e.key === "Enter") saveEdit(convId);
    if (e.key === "Escape") setEditingId(null);
  }

  function requestDelete(convId: string, e: React.MouseEvent) {
    e.stopPropagation();
    setDeletingId(convId);
  }

  async function confirmDelete(convId: string, e: React.MouseEvent) {
    e.stopPropagation();
    // Firestore no elimina subcollecciones automáticamente: borrar messages/ primero
    const messagesRef = collection(db, "conversations", convId, "messages");
    const msgSnap = await getDocs(messagesRef).catch(() => null);
    if (msgSnap && !msgSnap.empty) {
      const batch = writeBatch(db);
      msgSnap.docs.forEach((msgDoc) => batch.delete(msgDoc.ref));
      await batch.commit().catch(() => {});
    }
    await deleteDoc(doc(db, "conversations", convId)).catch(() => {});
    setDeletingId(null);
    // Si se eliminó la conversación activa, iniciar un chat nuevo
    if (convId === activeConversationId) onNewChat();
  }

  function cancelDelete(e: React.MouseEvent) {
    e.stopPropagation();
    setDeletingId(null);
  }

  function formatDate(date: Date): string {
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / 86_400_000);
    if (days === 0) return "Hoy";
    if (days === 1) return "Ayer";
    if (days < 7) return `Hace ${days} días`;
    return date.toLocaleDateString("es-CO", {
      day: "numeric",
      month: "short",
    });
  }

  return (
    <>
      {/* Backdrop para cerrar en mobile */}
      <div
        className="fixed inset-0 z-30 bg-foreground/20 md:hidden"
        onClick={onClose}
        aria-hidden="true"
      />

      <motion.aside
        className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-border bg-surface md:relative md:z-auto"
        initial={{ x: -264 }}
        animate={{ x: 0 }}
        exit={{ x: -264 }}
        transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
        aria-label="Historial de conversaciones"
      >
        {/* Cabecera del sidebar */}
        <div className="flex items-center justify-between border-b border-border px-3 py-3">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted">
            Conversaciones
          </span>
          <button
            onClick={onClose}
            aria-label="Cerrar panel"
            className="rounded-md p-1 text-muted transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="m15 18-6-6 6-6" />
            </svg>
          </button>
        </div>

        {/* Botón nuevo chat */}
        <div className="border-b border-border px-3 py-2">
          <button
            onClick={() => {
              onNewChat();
              onClose();
            }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted transition-colors hover:bg-accent/8 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 5v14M5 12h14" />
            </svg>
            Nueva consulta
          </button>
        </div>

        {/* Búsqueda */}
        <div className="border-b border-border px-3 py-2">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar…"
            className="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>

        {/* Lista de conversaciones */}
        <div className="flex-1 overflow-y-auto py-1">
          {loading && conversations.length === 0 && (
            <p className="px-4 py-6 text-center text-xs text-muted">
              Cargando…
            </p>
          )}

          {!loading && filtered.length === 0 && (
            <p className="px-4 py-6 text-center text-xs text-muted">
              {search ? "Sin resultados" : "Sin conversaciones"}
            </p>
          )}

          {filtered.map((conv) => {
            const isActive = conv.id === activeConversationId;
            const isDeleting = deletingId === conv.id;
            const isEditing = editingId === conv.id;

            return (
              <div
                key={conv.id}
                className={`group relative mx-1 my-0.5 cursor-pointer rounded-lg px-3 py-2 transition-colors ${
                  isActive
                    ? "bg-accent/10 text-foreground"
                    : "text-muted hover:bg-accent/6 hover:text-foreground"
                }`}
                onClick={() => !isEditing && onSelectConversation(conv)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) =>
                  e.key === "Enter" && !isEditing && onSelectConversation(conv)
                }
                aria-current={isActive ? "true" : undefined}
              >
                {/* Título o input de edición */}
                {isEditing ? (
                  <input
                    ref={editInputRef}
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onBlur={() => saveEdit(conv.id)}
                    onKeyDown={(e) => handleEditKeyDown(e, conv.id)}
                    maxLength={60}
                    className="w-full rounded border border-accent bg-background px-1 py-0.5 text-xs text-foreground focus:outline-none"
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <p className="truncate text-xs font-medium leading-snug">
                    {conv.title}
                  </p>
                )}

                {/* Fecha */}
                {!isEditing && (
                  <p className="mt-0.5 text-[10px] text-muted/70">
                    {formatDate(conv.updatedAt)}
                  </p>
                )}

                {/* Acciones: editar + eliminar */}
                {!isEditing && !isDeleting && (
                  <div className="absolute right-2 top-1/2 hidden -translate-y-1/2 items-center gap-0.5 group-hover:flex">
                    <button
                      onClick={(e) => startEdit(conv, e)}
                      aria-label="Editar título"
                      className="rounded p-1 text-muted transition-colors hover:text-foreground"
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="12"
                        height="12"
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
                    </button>
                    <button
                      onClick={(e) => requestDelete(conv.id, e)}
                      aria-label="Eliminar conversación"
                      className="rounded p-1 text-muted transition-colors hover:text-red-500"
                    >
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="12"
                        height="12"
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
                    </button>
                  </div>
                )}

                {/* Confirmación de borrado */}
                {isDeleting && (
                  <div className="mt-1 flex items-center gap-1.5">
                    <span className="text-[10px] text-muted">¿Eliminar?</span>
                    <button
                      onClick={(e) => confirmDelete(conv.id, e)}
                      className="rounded px-1.5 py-0.5 text-[10px] font-medium text-red-600 transition-colors hover:bg-red-50"
                    >
                      Sí
                    </button>
                    <button
                      onClick={cancelDelete}
                      className="rounded px-1.5 py-0.5 text-[10px] text-muted transition-colors hover:text-foreground"
                    >
                      No
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </motion.aside>
    </>
  );
}
