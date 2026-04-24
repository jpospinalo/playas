"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { collection, deleteDoc, doc, getDocs, updateDoc, writeBatch } from "firebase/firestore";
import { useAuth } from "@/components/providers/AuthProvider";
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
  const { user, signOut } = useAuth();
  const [search, setSearch] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const editInputRef = useRef<HTMLInputElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const searchResults = conversations.filter((c) =>
    c.title.toLowerCase().includes(search.toLowerCase())
  );
  const hasSearch = search.trim().length > 0;
  const userEmail = user?.email ?? "usuario@correo.com";
  const userName = user?.displayName ?? userEmail.split("@")[0] ?? "Usuario";
  const userInitial = userName[0]?.toUpperCase() ?? "U";

  useEffect(() => {
    if (editingId) editInputRef.current?.focus();
  }, [editingId]);

  useEffect(() => {
    if (searchOpen) searchInputRef.current?.focus();
  }, [searchOpen]);

  useEffect(() => {
    if (!menuOpenId && !profileOpen && !searchOpen) return;

    const closeFloatingPanels = (e: MouseEvent) => {
      const target = e.target as Element;
      if (target.closest("[data-conversation-menu-root]")) return;
      if (target.closest("[data-user-menu-root]")) return;
      if (target.closest("[data-conversation-search-dialog]")) return;
      setMenuOpenId(null);
      setProfileOpen(false);
    };

    const closeOnEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuOpenId(null);
        setProfileOpen(false);
        setSearchOpen(false);
      }
    };

    document.addEventListener("mousedown", closeFloatingPanels);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeFloatingPanels);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [menuOpenId, profileOpen, searchOpen]);

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
    setSearchOpen(false);
    setProfileOpen(false);
    setDeletingId(null);
    setEditingId(null);
    onNewChat();
  }

  function handleToggleSidebar() {
    setMenuOpenId(null);
    setSearchOpen(false);
    setProfileOpen(false);
    onToggleSidebar();
  }

  function handleCollapsedSearch() {
    setMenuOpenId(null);
    setProfileOpen(false);
    setSearchOpen(true);
    if (!isExpanded) onToggleSidebar();
  }

  async function handleSelectConversation(conv: Conversation) {
    setSearchOpen(false);
    setMenuOpenId(null);
    setProfileOpen(false);
    await onSelectConversation(conv);
  }

  async function handleSignOut() {
    setProfileOpen(false);
    await signOut();
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
            <div className="flex items-center justify-between px-3 py-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted">
                Conversaciones
              </span>
              <button
                onClick={handleToggleSidebar}
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
            <div className="px-3 py-2">
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
            <div className="px-3 py-2">
              <button
                type="button"
                onClick={() => {
                  setMenuOpenId(null);
                  setProfileOpen(false);
                  setSearchOpen(true);
                }}
                aria-label="Buscar conversaciones"
                aria-haspopup="dialog"
                aria-expanded={searchOpen}
                className={`flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                  searchOpen || hasSearch
                    ? "bg-accent-light text-accent"
                    : "text-muted hover:bg-accent/8 hover:text-foreground"
                }`}
              >
                <span className="flex min-w-0 items-center gap-2">
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
                    className="shrink-0"
                  >
                    <circle cx="11" cy="11" r="8" />
                    <path d="m21 21-4.35-4.35" />
                  </svg>
                  <span className="truncate">
                    Buscar conversaciones
                  </span>
                </span>
                {hasSearch && (
                  <span className="shrink-0 rounded-full bg-surface px-1.5 py-0.5 text-[10px] font-semibold text-accent shadow-sm">
                    {searchResults.length}
                  </span>
                )}
              </button>
            </div>

            {/* Lista de conversaciones */}
            <div className="flex-1 overflow-y-auto py-1">
              {loading && conversations.length === 0 && (
                <p className="px-4 py-6 text-center text-xs text-muted">
                  Cargando…
                </p>
              )}

              {!loading && conversations.length === 0 && (
                <p className="px-4 py-6 text-center text-xs text-muted">
                  Sin conversaciones
                </p>
              )}

              {conversations.map((conv) => {
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

            <div className="relative p-2" data-user-menu-root>
              <button
                type="button"
                onClick={() => {
                  setMenuOpenId(null);
                  setSearchOpen(false);
                  setProfileOpen((current) => !current);
                }}
                aria-label="Abrir menú de perfil"
                aria-haspopup="menu"
                aria-expanded={profileOpen}
                className="flex w-full items-center gap-2 rounded-xl px-2 py-2 text-left transition-colors hover:bg-accent/8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-navy text-xs font-semibold text-white">
                  {userInitial}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-semibold text-foreground">
                    {userName}
                  </span>
                  <span className="block truncate text-[10px] text-muted">
                    {userEmail}
                  </span>
                </span>
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
                  className="shrink-0 text-muted"
                >
                  <path d="m6 9 6 6 6-6" />
                </svg>
              </button>

              <AnimatePresence>
                {profileOpen && (
                  <motion.div
                    role="menu"
                    className="absolute bottom-14 left-2 right-2 z-50 rounded-2xl border border-border bg-surface p-2 shadow-xl shadow-foreground/10"
                    initial={{ opacity: 0, y: 6, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 6, scale: 0.98 }}
                    transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                  >
                    <div className="border-b border-border px-2 py-2">
                      <p className="truncate text-sm font-semibold text-foreground">
                        {userName}
                      </p>
                      <p className="truncate text-xs text-muted">{userEmail}</p>
                    </div>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={handleSignOut}
                      className="mt-1 flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-sm text-red-600 transition-colors hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
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
                        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                        <path d="m16 17 5-5-5-5" />
                        <path d="M21 12H9" />
                      </svg>
                      Cerrar sesión
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
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
          onClick={handleToggleSidebar}
          aria-hidden="true"
        />
      )}

      {/* Desktop: sidebar persistente con ancho animado */}
      <motion.aside
        className="hidden flex-none overflow-visible bg-surface md:flex md:flex-col"
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
                onClick={handleToggleSidebar}
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

              <button
                onClick={handleCollapsedSearch}
                aria-label="Buscar conversaciones"
                title="Buscar conversaciones"
                className={`flex h-10 w-10 items-center justify-center rounded-lg transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 ${
                  hasSearch
                    ? "bg-accent-light text-accent"
                    : "text-muted hover:bg-accent/8 hover:text-foreground"
                }`}
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
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.35-4.35" />
                </svg>
              </button>

              <div className="relative mt-auto pb-2" data-user-menu-root>
                <button
                  type="button"
                  onClick={() => {
                    setMenuOpenId(null);
                    setSearchOpen(false);
                    setProfileOpen((current) => !current);
                  }}
                  aria-label="Abrir menú de perfil"
                  aria-haspopup="menu"
                  aria-expanded={profileOpen}
                  title={userEmail}
                  className="flex h-10 w-10 items-center justify-center rounded-full bg-navy text-xs font-semibold text-white transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2"
                >
                  {userInitial}
                </button>

                <AnimatePresence>
                  {profileOpen && (
                    <motion.div
                      role="menu"
                      className="absolute bottom-14 left-2 z-50 w-56 rounded-2xl border border-border bg-surface p-2 shadow-xl shadow-foreground/10"
                      initial={{ opacity: 0, x: -4, y: 6, scale: 0.98 }}
                      animate={{ opacity: 1, x: 0, y: 0, scale: 1 }}
                      exit={{ opacity: 0, x: -4, y: 6, scale: 0.98 }}
                      transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                    >
                      <div className="border-b border-border px-2 py-2">
                        <p className="truncate text-sm font-semibold text-foreground">
                          {userName}
                        </p>
                        <p className="truncate text-xs text-muted">{userEmail}</p>
                      </div>
                      <button
                        type="button"
                        role="menuitem"
                        onClick={handleSignOut}
                        className="mt-1 flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-sm text-red-600 transition-colors hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
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
                          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                          <path d="m16 17 5-5-5-5" />
                          <path d="M21 12H9" />
                        </svg>
                        Cerrar sesión
                      </button>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.aside>

      {/* Mobile: overlay */}
      <AnimatePresence>
        {isExpanded && (
          <motion.aside
            className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-surface md:hidden"
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

      <AnimatePresence>
        {searchOpen && (
          <motion.div
            className="fixed inset-0 z-50 flex items-start justify-center bg-foreground/30 px-4 pt-[12vh] backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.16 }}
            aria-hidden="false"
          >
            <button
              type="button"
              className="absolute inset-0 cursor-default"
              aria-label="Cerrar búsqueda"
              onClick={() => setSearchOpen(false)}
            />
            <motion.div
              role="dialog"
              aria-modal="true"
              aria-label="Buscar conversaciones"
              data-conversation-search-dialog
              className="relative z-10 flex max-h-[72vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-foreground/20"
              initial={{ opacity: 0, y: 18, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.98 }}
              transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            >
              <div className="border-b border-border p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <h2 className="text-sm font-semibold text-foreground">
                      Buscar chats
                    </h2>
                    <p className="mt-0.5 text-xs text-muted">
                      Encuentra una conversación por título y ábrela al instante.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSearchOpen(false)}
                    aria-label="Cerrar búsqueda"
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted transition-colors hover:bg-accent/8 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
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
                      <path d="M18 6 6 18M6 6l12 12" />
                    </svg>
                  </button>
                </div>

                <label htmlFor="conversation-search-dialog" className="sr-only">
                  Buscar conversaciones
                </label>
                <div className="flex items-center gap-3 rounded-xl border border-border bg-background px-3 py-2.5 transition-[border-color,box-shadow] duration-150 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/15">
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
                    className="shrink-0 text-muted"
                  >
                    <circle cx="11" cy="11" r="8" />
                    <path d="m21 21-4.35-4.35" />
                  </svg>
                  <input
                    ref={searchInputRef}
                    id="conversation-search-dialog"
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Buscar conversaciones..."
                    className="min-w-0 flex-1 bg-transparent text-sm text-foreground placeholder:text-muted/60 focus:outline-none"
                  />
                  {hasSearch && (
                    <button
                      type="button"
                      onClick={() => {
                        setSearch("");
                        searchInputRef.current?.focus();
                      }}
                      aria-label="Limpiar búsqueda"
                      className="shrink-0 rounded-lg px-2 py-1 text-xs font-medium text-muted transition-colors hover:bg-accent/8 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                    >
                      Limpiar
                    </button>
                  )}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-2">
                <div className="px-2 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted/70">
                  {hasSearch
                    ? `${searchResults.length} resultado${searchResults.length === 1 ? "" : "s"}`
                    : "Conversaciones recientes"}
                </div>

                {loading && conversations.length === 0 && (
                  <p className="px-3 py-8 text-center text-sm text-muted">
                    Cargando conversaciones...
                  </p>
                )}

                {!loading && searchResults.length === 0 && (
                  <div className="px-4 py-10 text-center">
                    <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-accent-light text-accent">
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <circle cx="11" cy="11" r="8" />
                        <path d="m21 21-4.35-4.35" />
                      </svg>
                    </div>
                    <p className="text-sm font-medium text-foreground">
                      No encontramos conversaciones
                    </p>
                    <p className="mt-1 text-xs text-muted">
                      Prueba con otra palabra del título.
                    </p>
                  </div>
                )}

                {searchResults.map((conv) => {
                  const isActive = conv.id === activeConversationId;

                  return (
                    <button
                      key={conv.id}
                      type="button"
                      onClick={() => handleSelectConversation(conv)}
                      className={`group flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                        isActive
                          ? "bg-accent/10 text-foreground"
                          : "text-muted hover:bg-accent/6 hover:text-foreground"
                      }`}
                    >
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-background text-muted transition-colors group-hover:border-accent/30 group-hover:text-accent">
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
                          <path d="M21 15a4 4 0 0 1-4 4H7l-4 4V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
                        </svg>
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">
                          {conv.title}
                        </span>
                        <span className="mt-0.5 block text-xs text-muted/70">
                          {formatDate(conv.updatedAt)}
                          {conv.messageCount > 0
                            ? ` · ${conv.messageCount} mensajes`
                            : ""}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
