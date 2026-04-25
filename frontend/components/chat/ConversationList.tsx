"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import { AnimatePresence, motion } from "motion/react";
import { collection, deleteDoc, doc, getDocs, updateDoc, writeBatch } from "firebase/firestore";
import { db } from "@/lib/firebase";
import type { Conversation } from "@/hooks/useConversations";
import { formatConversationDate } from "@/components/chat/conversationSidebarUtils";

interface ConversationListProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  loading: boolean;
  onSelectConversation: (conv: Conversation) => Promise<void>;
  onNewChat: () => void;
}

export function ConversationList({
  conversations,
  activeConversationId,
  loading,
  onSelectConversation,
  onNewChat,
}: ConversationListProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const editInputRef = useRef<HTMLInputElement>(null);

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

  function handleEditKeyDown(event: KeyboardEvent, convId: string) {
    if (event.key === "Enter") saveEdit(convId);
    if (event.key === "Escape") setEditingId(null);
  }

  function requestDelete(convId: string, event: MouseEvent) {
    event.stopPropagation();
    setMenuOpenId(null);
    setEditingId(null);
    setDeletingId(convId);
  }

  async function confirmDelete(convId: string, event: MouseEvent) {
    event.stopPropagation();

    const messagesRef = collection(db, "conversations", convId, "messages");
    const msgSnap = await getDocs(messagesRef).catch(() => null);
    if (msgSnap && !msgSnap.empty) {
      const batch = writeBatch(db);
      msgSnap.docs.forEach((msgDoc) => batch.delete(msgDoc.ref));
      await batch.commit().catch(() => {});
    }

    await deleteDoc(doc(db, "conversations", convId)).catch(() => {});
    setDeletingId(null);

    if (convId === activeConversationId) onNewChat();
  }

  function cancelDelete(event: MouseEvent) {
    event.stopPropagation();
    setDeletingId(null);
  }

  if (loading && conversations.length === 0) {
    return <p className="px-4 py-6 text-center text-xs text-muted">Cargando...</p>;
  }

  if (!loading && conversations.length === 0) {
    return (
      <p className="px-4 py-6 text-center text-xs text-muted">
        Sin conversaciones
      </p>
    );
  }

  return (
    <>
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
                {isEditing ? (
                  <input
                    ref={editInputRef}
                    value={editTitle}
                    onChange={(event) => setEditTitle(event.target.value)}
                    onBlur={() => saveEdit(conv.id)}
                    onKeyDown={(event) => handleEditKeyDown(event, conv.id)}
                    maxLength={60}
                    className="w-full rounded border border-accent bg-background px-1 py-0.5 text-xs text-foreground focus:outline-none"
                    onClick={(event) => event.stopPropagation()}
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
                      {formatConversationDate(conv.updatedAt)}
                    </p>
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
            </div>

            {isDeleting && (
              <DeleteConfirmation
                onConfirm={(event) => confirmDelete(conv.id, event)}
                onCancel={cancelDelete}
              />
            )}
          </div>
        );
      })}
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
    <div className="relative -mr-1 mt-0.5 shrink-0" data-conversation-menu-root>
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          onToggle();
        }}
        aria-label={`Opciones para ${conversation.title}`}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        className="flex h-7 w-7 items-center justify-center rounded-md text-muted opacity-0 transition-[background-color,color,opacity] duration-150 hover:bg-accent/8 hover:text-foreground focus:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent group-hover:opacity-100 group-focus-within:opacity-100"
      >
        <DotsIcon />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            role="menu"
            className="absolute right-0 top-8 z-50 w-40 rounded-xl border border-border bg-surface p-1 shadow-lg shadow-foreground/10"
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
              className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs text-red-600 transition-colors hover:bg-red-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
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
  onConfirm,
  onCancel,
}: {
  onConfirm: (event: MouseEvent) => void;
  onCancel: (event: MouseEvent) => void;
}) {
  return (
    <div
      className="mt-2 rounded-lg border border-red-200 bg-red-50 px-2.5 py-2"
      onClick={(event) => event.stopPropagation()}
    >
      <p className="text-[10px] font-medium text-red-700">
        ¿Eliminar esta conversación?
      </p>
      <div className="mt-1.5 flex items-center gap-1.5">
        <button
          onClick={onConfirm}
          className="rounded-md bg-red-600 px-2 py-1 text-[10px] font-medium text-white transition-colors hover:bg-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2"
        >
          Eliminar
        </button>
        <button
          onClick={onCancel}
          className="rounded-md px-2 py-1 text-[10px] text-muted transition-colors hover:bg-surface hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
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
