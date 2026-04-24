"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { collection, deleteDoc, doc, getDocs, updateDoc, writeBatch } from "firebase/firestore";
import { db } from "@/lib/firebase";
import type { Conversation } from "@/hooks/useConversations";

interface ConversationSidebarProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  loading: boolean;
  isExpanded: boolean;
  transitionEnabled: boolean;
  onSelectConversation: (conv: Conversation) => Promise<void>;
  onNewChat: () => void;
  onToggleSidebar: () => void;
}

const SIDEBAR_EXPANDED_WIDTH = 272;
const SIDEBAR_COLLAPSED_WIDTH = 56;
const SIDEBAR_TRANSITION = { duration: 0.22, ease: [0.16, 1, 0.3, 1] } as const;

export function ConversationSidebar({
  conversations,
  activeConversationId,
  loading,
  isExpanded,
  transitionEnabled,
  onSelectConversation,
  onNewChat,
  onToggleSidebar,
}: ConversationSidebarProps) {
  const [search, setSearch] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const editInputRef = useRef<HTMLInputElement>(null);

  const filtered = conversations.filter((c) =>
    c.title.toLowerCase().includes(search.toLowerCase())
  );

  useEffect(() => {
    if (editingId) editInputRef.current?.focus();
  }, [editingId]);

  useEffect(() => {
    if (!menuOpenId) return;

    const closeMenu = (e: MouseEvent) => {
      const target = e.target as Element;
      if (target.closest("[data-conversation-menu-root]")) return;
      setMenuOpenId(null);
    };

    const closeOnEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpenId(null);
    };

    document.addEventListener("mousedown", closeMenu);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeMenu);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [menuOpenId]);

  function startEdit(conv: Conversation, e: React.MouseEvent) {
    e.stopPropagation();
    setMenuOpenId(null);
    setDeletingId(null);
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
    setMenuOpenId(null);
    setEditingId(null);
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

  function handleNewChat() {
    setMenuOpenId(null);
    setDeletingId(null);
    setEditingId(null);
    onNewChat();
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

  function renderExpandedContent() {
    return (
      <>
            {/* Cabecera del sidebar */}
            <div className="flex items-center justify-between border-b border-border px-3 py-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted">
                Conversaciones
              </span>
              <button
                onClick={onToggleSidebar}
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
                onClick={handleNewChat}
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
                    className={`group relative mx-1 my-0.5 rounded-lg px-3 py-2 transition-colors ${
                      isActive
                        ? "bg-accent/10 text-foreground"
                        : "text-muted hover:bg-accent/6 hover:text-foreground"
                    }`}
                    aria-current={isActive ? "true" : undefined}
                  >
                    <div className="flex items-start gap-2">
                      <div className="min-w-0 flex-1">
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
                          <button
                            type="button"
                            onClick={() => onSelectConversation(conv)}
                            className="block w-full min-w-0 cursor-pointer rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                          >
                            <p className="truncate pr-1 text-xs font-medium leading-snug">
                              {conv.title}
                            </p>
                            <p className="mt-0.5 text-[10px] text-muted/70">
                              {formatDate(conv.updatedAt)}
                            </p>
                          </button>
                        )}
                      </div>

                      {/* Menú de acciones */}
                      {!isEditing && !isDeleting && (
                        <div
                          className="relative -mr-1 mt-0.5 shrink-0"
                          data-conversation-menu-root
                        >
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setMenuOpenId((current) =>
                                current === conv.id ? null : conv.id
                              );
                            }}
                            aria-label={`Opciones para ${conv.title}`}
                            aria-haspopup="menu"
                            aria-expanded={menuOpenId === conv.id}
                            className="flex h-7 w-7 items-center justify-center rounded-md text-muted opacity-0 transition-[background-color,color,opacity] duration-150 hover:bg-accent/8 hover:text-foreground focus:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent group-hover:opacity-100 group-focus-within:opacity-100"
                          >
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
                          </button>

                          <AnimatePresence>
                            {menuOpenId === conv.id && (
                              <motion.div
                                role="menu"
                                className="absolute right-0 top-8 z-50 w-40 rounded-xl border border-border bg-surface p-1 shadow-lg shadow-foreground/10"
                                initial={{ opacity: 0, y: -4, scale: 0.98 }}
                                animate={{ opacity: 1, y: 0, scale: 1 }}
                                exit={{ opacity: 0, y: -4, scale: 0.98 }}
                                transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                                onClick={(e) => e.stopPropagation()}
                              >
                                <button
                                  type="button"
                                  role="menuitem"
                                  onClick={(e) => startEdit(conv, e)}
                                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs text-muted transition-colors hover:bg-accent/8 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                                >
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
                                  Renombrar
                                </button>
                                <button
                                  type="button"
                                  role="menuitem"
                                  onClick={(e) => requestDelete(conv.id, e)}
                                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs text-red-600 transition-colors hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
                                >
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
                                  Eliminar
                                </button>
                              </motion.div>
                            )}
                          </AnimatePresence>
                        </div>
                      )}
                    </div>

                    {/* Confirmación de borrado */}
                    {isDeleting && (
                      <div
                        className="mt-2 rounded-lg border border-red-200 bg-red-50 px-2.5 py-2"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <p className="text-[10px] font-medium text-red-700">
                          ¿Eliminar esta conversación?
                        </p>
                        <div className="mt-1.5 flex items-center gap-1.5">
                          <button
                            onClick={(e) => confirmDelete(conv.id, e)}
                            className="rounded-md bg-red-600 px-2 py-1 text-[10px] font-medium text-white transition-colors hover:bg-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2"
                          >
                            Eliminar
                          </button>
                          <button
                            onClick={cancelDelete}
                            className="rounded-md px-2 py-1 text-[10px] text-muted transition-colors hover:bg-surface hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                          >
                            Cancelar
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
      </>
    );
  }

  return (
    <>
      {/* Backdrop para cerrar en mobile (solo cuando está expandido) */}
      {isExpanded && (
        <div
          className="fixed inset-0 z-30 bg-foreground/20 md:hidden"
          onClick={onToggleSidebar}
          aria-hidden="true"
        />
      )}

      {/* Desktop: sidebar persistente con ancho animado */}
      <motion.aside
        className="hidden flex-none overflow-visible border-r border-border bg-surface md:flex md:flex-col"
        initial={false}
        animate={{
          width: isExpanded ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_COLLAPSED_WIDTH,
        }}
        transition={transitionEnabled ? SIDEBAR_TRANSITION : { duration: 0 }}
        aria-label={isExpanded ? "Historial de conversaciones" : "Panel de conversaciones"}
      >
        <AnimatePresence mode="wait" initial={false}>
          {isExpanded ? (
            <motion.div
              key="expanded"
              className="flex h-full min-w-0 flex-col overflow-hidden"
              initial={transitionEnabled ? { opacity: 0 } : false}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: transitionEnabled ? 0.12 : 0 }}
            >
              {renderExpandedContent()}
            </motion.div>
          ) : (
            <motion.div
              key="collapsed"
              className="flex h-full flex-col items-center gap-1 pt-2"
              initial={transitionEnabled ? { opacity: 0 } : false}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: transitionEnabled ? 0.12 : 0 }}
            >
              <button
                onClick={onToggleSidebar}
                aria-label="Abrir historial"
                title="Abrir historial"
                className="flex h-10 w-10 items-center justify-center rounded-lg text-muted transition-colors duration-150 hover:bg-accent/8 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <rect width="18" height="18" x="3" y="3" rx="2" />
                  <path d="M9 3v18" />
                </svg>
              </button>

              <button
                onClick={handleNewChat}
                aria-label="Nueva consulta"
                title="Nueva consulta"
                className="flex h-10 w-10 items-center justify-center rounded-lg text-muted transition-colors duration-150 hover:bg-accent/8 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
              >
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
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.aside>

      {/* Mobile: overlay */}
      <AnimatePresence>
        {isExpanded && (
          <motion.aside
            className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-border bg-surface md:hidden"
            initial={{ x: -264 }}
            animate={{ x: 0 }}
            exit={{ x: -264 }}
            transition={SIDEBAR_TRANSITION}
            aria-label="Historial de conversaciones"
          >
            {renderExpandedContent()}
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}
