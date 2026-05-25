"use client";

import { useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useAuth } from "@/components/providers/AuthProvider";
import { ConversationList } from "@/components/chat/ConversationList";
import { ConversationSearchDialog } from "@/components/chat/ConversationSearchDialog";
import { SidebarUserMenu } from "@/components/chat/SidebarUserMenu";
import {
  SIDEBAR_COLLAPSED_WIDTH,
  SIDEBAR_EXPANDED_WIDTH,
  SIDEBAR_TRANSITION,
} from "@/components/chat/conversationSidebarUtils";
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
  const { user, role, signOut } = useAuth();
  const [search, setSearch] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const isAdmin = role === "admin" || role === "super-admin";

  const searchResults = conversations.filter((conversation) =>
    conversation.title.toLowerCase().includes(search.toLowerCase())
  );
  const hasSearch = search.trim().length > 0;
  const userInfo = getUserInfo(user);

  function closePanels() {
    setSearchOpen(false);
    setProfileOpen(false);
  }

  function handleNewChat() {
    closePanels();
    onNewChat();
  }

  function handleToggleSidebar() {
    closePanels();
    onToggleSidebar();
  }

  function openSearch() {
    setProfileOpen(false);
    setSearchOpen(true);
  }

  async function handleSelectConversation(conv: Conversation) {
    closePanels();
    await onSelectConversation(conv);
  }

  async function handleSignOut() {
    setProfileOpen(false);
    await signOut();
  }

  return (
    <>
      {isExpanded && (
        <div
          className="fixed inset-0 z-30 bg-foreground/20 md:hidden"
          onClick={handleToggleSidebar}
          aria-hidden="true"
        />
      )}

      <DesktopSidebar
        expanded={isExpanded}
        transitionEnabled={transitionEnabled}
        hasSearch={hasSearch}
        profileOpen={profileOpen}
        userInfo={userInfo}
        isAdmin={isAdmin}
        conversations={conversations}
        activeConversationId={activeConversationId}
        loading={loading}
        onToggleSidebar={handleToggleSidebar}
        onNewChat={handleNewChat}
        onOpenSearch={openSearch}
        onCollapsedSearch={openSearch}
        onToggleProfile={() => {
          setSearchOpen(false);
          setProfileOpen((current) => !current);
        }}
        onCloseProfile={() => setProfileOpen(false)}
        onSignOut={handleSignOut}
        onSelectConversation={handleSelectConversation}
      />

      <MobileSidebar
        open={isExpanded}
        hasSearch={hasSearch}
        profileOpen={profileOpen}
        userInfo={userInfo}
        isAdmin={isAdmin}
        conversations={conversations}
        activeConversationId={activeConversationId}
        loading={loading}
        onToggleSidebar={handleToggleSidebar}
        onNewChat={handleNewChat}
        onOpenSearch={openSearch}
        onToggleProfile={() => {
          setSearchOpen(false);
          setProfileOpen((current) => !current);
        }}
        onCloseProfile={() => setProfileOpen(false)}
        onSignOut={handleSignOut}
        onSelectConversation={handleSelectConversation}
      />

      <ConversationSearchDialog
        open={searchOpen}
        search={search}
        conversations={conversations}
        results={searchResults}
        activeConversationId={activeConversationId}
        loading={loading}
        onSearchChange={setSearch}
        onClose={() => setSearchOpen(false)}
        onSelectConversation={handleSelectConversation}
      />
    </>
  );
}

interface SidebarContentProps {
  hasSearch: boolean;
  profileOpen: boolean;
  userInfo: UserInfo;
  isAdmin: boolean;
  conversations: Conversation[];
  activeConversationId: string | null;
  loading: boolean;
  onToggleSidebar: () => void;
  onNewChat: () => void;
  onOpenSearch: () => void;
  onToggleProfile: () => void;
  onCloseProfile: () => void;
  onSignOut: () => Promise<void>;
  onSelectConversation: (conv: Conversation) => Promise<void>;
}

function DesktopSidebar({
  expanded,
  transitionEnabled,
  hasSearch,
  profileOpen,
  userInfo,
  isAdmin,
  conversations,
  activeConversationId,
  loading,
  onToggleSidebar,
  onNewChat,
  onOpenSearch,
  onCollapsedSearch,
  onToggleProfile,
  onCloseProfile,
  onSignOut,
  onSelectConversation,
}: SidebarContentProps & {
  expanded: boolean;
  transitionEnabled: boolean;
  onCollapsedSearch: () => void;
}) {
  return (
    <motion.aside
      className={`hidden flex-none overflow-visible md:flex md:flex-col ${
        expanded
          ? "border-r border-border bg-elevated/60 backdrop-blur-md"
          : "bg-transparent"
      }`}
      initial={false}
      animate={{
        width: expanded ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_COLLAPSED_WIDTH,
      }}
      transition={transitionEnabled ? SIDEBAR_TRANSITION : { duration: 0 }}
      aria-label={expanded ? "Historial de conversaciones" : "Panel de conversaciones"}
    >
      <AnimatePresence mode="wait" initial={false}>
        {expanded ? (
          <motion.div
            key="expanded"
            className="flex h-full min-w-0 flex-col overflow-hidden"
            initial={transitionEnabled ? { opacity: 0 } : false}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: transitionEnabled ? 0.12 : 0 }}
          >
            <ExpandedSidebarContent
              hasSearch={hasSearch}
              profileOpen={profileOpen}
              userInfo={userInfo}
              isAdmin={isAdmin}
              conversations={conversations}
              activeConversationId={activeConversationId}
              loading={loading}
              onToggleSidebar={onToggleSidebar}
              onNewChat={onNewChat}
              onOpenSearch={onOpenSearch}
              onToggleProfile={onToggleProfile}
              onCloseProfile={onCloseProfile}
              onSignOut={onSignOut}
              onSelectConversation={onSelectConversation}
            />
          </motion.div>
        ) : (
          <CollapsedSidebarContent
            hasSearch={hasSearch}
            profileOpen={profileOpen}
            userInfo={userInfo}
            isAdmin={isAdmin}
            onToggleSidebar={onToggleSidebar}
            onNewChat={onNewChat}
            onOpenSearch={onCollapsedSearch}
            onToggleProfile={onToggleProfile}
            onCloseProfile={onCloseProfile}
            onSignOut={onSignOut}
            transitionEnabled={transitionEnabled}
          />
        )}
      </AnimatePresence>
    </motion.aside>
  );
}

function MobileSidebar({
  open,
  hasSearch,
  profileOpen,
  userInfo,
  isAdmin,
  conversations,
  activeConversationId,
  loading,
  onToggleSidebar,
  onNewChat,
  onOpenSearch,
  onToggleProfile,
  onCloseProfile,
  onSignOut,
  onSelectConversation,
}: SidebarContentProps & { open: boolean }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-border bg-surface md:hidden"
          initial={{ x: -264 }}
          animate={{ x: 0 }}
          exit={{ x: -264 }}
          transition={SIDEBAR_TRANSITION}
          aria-label="Historial de conversaciones"
        >
          <ExpandedSidebarContent
            hasSearch={hasSearch}
            profileOpen={profileOpen}
            userInfo={userInfo}
            isAdmin={isAdmin}
            conversations={conversations}
            activeConversationId={activeConversationId}
            loading={loading}
            onToggleSidebar={onToggleSidebar}
            onNewChat={onNewChat}
            onOpenSearch={onOpenSearch}
            onToggleProfile={onToggleProfile}
            onCloseProfile={onCloseProfile}
            onSignOut={onSignOut}
            onSelectConversation={onSelectConversation}
          />
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

function ExpandedSidebarContent({
  hasSearch,
  profileOpen,
  userInfo,
  isAdmin,
  conversations,
  activeConversationId,
  loading,
  onToggleSidebar,
  onNewChat,
  onOpenSearch,
  onToggleProfile,
  onCloseProfile,
  onSignOut,
  onSelectConversation,
}: SidebarContentProps) {
  const hasConversations = conversations.length > 0;
  return (
    <>
      <SidebarHeader onToggleSidebar={onToggleSidebar} />

      <div className="px-2 pt-1">
        <SidebarPillButton
          label="Nueva consulta"
          icon={<PencilEditIcon />}
          emphasis="primary"
          onClick={onNewChat}
        />
        <SidebarPillButton
          label="Buscar conversaciones"
          icon={<SearchIcon />}
          emphasis={hasSearch ? "active" : "default"}
          onClick={onOpenSearch}
        />
      </div>

      <div className="flex-1 overflow-y-auto">
        {(hasConversations || loading) && (
          <p className="px-5 pb-1 pt-5 text-[11px] font-medium text-subtle">
            Recientes
          </p>
        )}
        <ConversationList
          conversations={conversations}
          activeConversationId={activeConversationId}
          loading={loading}
          onSelectConversation={onSelectConversation}
          onNewChat={onNewChat}
        />
      </div>

      <SidebarUserMenu
        expanded
        open={profileOpen}
        userName={userInfo.name}
        userEmail={userInfo.email}
        userInitial={userInfo.initial}
        isAdmin={isAdmin}
        onToggle={onToggleProfile}
        onClose={onCloseProfile}
        onSignOut={onSignOut}
      />
    </>
  );
}

function CollapsedSidebarContent({
  hasSearch,
  profileOpen,
  userInfo,
  isAdmin,
  transitionEnabled,
  onToggleSidebar,
  onNewChat,
  onOpenSearch,
  onToggleProfile,
  onCloseProfile,
  onSignOut,
}: Pick<SidebarContentProps, "hasSearch" | "profileOpen" | "userInfo" | "isAdmin"> & {
  transitionEnabled: boolean;
  onToggleSidebar: () => void;
  onNewChat: () => void;
  onOpenSearch: () => void;
  onToggleProfile: () => void;
  onCloseProfile: () => void;
  onSignOut: () => Promise<void>;
}) {
  return (
    <motion.div
      key="collapsed"
      className="flex h-full flex-col items-center gap-1 px-1 pt-3"
      initial={transitionEnabled ? { opacity: 0 } : false}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: transitionEnabled ? 0.12 : 0 }}
    >
      <div className="mb-2 flex h-9 w-9 items-center justify-center" aria-hidden="true">
        <AtlasGlyph />
      </div>
      <RailButton
        label="Abrir historial"
        icon={<PanelIcon />}
        onClick={onToggleSidebar}
      />
      <RailButton
        label="Nueva consulta"
        icon={<PlusIcon />}
        onClick={onNewChat}
      />
      <RailButton
        label="Buscar conversaciones"
        icon={<SearchIcon />}
        active={hasSearch}
        onClick={onOpenSearch}
      />

      <div className="mt-auto pb-2">
        <SidebarUserMenu
          expanded={false}
          open={profileOpen}
          userName={userInfo.name}
          userEmail={userInfo.email}
          userInitial={userInfo.initial}
          isAdmin={isAdmin}
          onToggle={onToggleProfile}
          onClose={onCloseProfile}
          onSignOut={onSignOut}
        />
      </div>
    </motion.div>
  );
}

function AtlasGlyph() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-accent"
      aria-hidden="true"
    >
      <path d="M12 3 L20 20 L4 20 Z" opacity="0.4" />
      <path d="M12 3 L20 20" />
      <path d="M12 3 L4 20" />
      <path d="M8 14 H16" opacity="0.55" />
    </svg>
  );
}

function SidebarHeader({ onToggleSidebar }: { onToggleSidebar: () => void }) {
  return (
    <div className="flex items-center justify-between px-4 pb-2 pt-3">
      <div className="flex items-center gap-2">
        <AtlasGlyph />
        <span
          className="text-[15px] font-medium tracking-[0.04em] text-foreground"
          translate="no"
        >
          ATLAS
        </span>
      </div>
      <button
        onClick={onToggleSidebar}
        aria-label="Cerrar panel"
        title="Cerrar panel"
        className="flex h-8 w-8 items-center justify-center rounded-full text-muted transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <PanelIcon />
      </button>
    </div>
  );
}

function SidebarPillButton({
  label,
  icon,
  emphasis = "default",
  onClick,
}: {
  label: string;
  icon: ReactNode;
  emphasis?: "default" | "primary" | "active";
  onClick: () => void;
}) {
  const emphasisClasses =
    emphasis === "primary"
      ? "bg-elevated text-foreground hover:bg-surface"
      : emphasis === "active"
        ? "bg-accent-soft text-accent"
        : "text-muted hover:bg-elevated hover:text-foreground";

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className={`mt-1 flex w-full items-center gap-3 rounded-full px-4 py-2.5 text-[13.5px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${emphasisClasses}`}
    >
      <span className="flex h-4 w-4 shrink-0 items-center justify-center">{icon}</span>
      <span className="truncate">{label}</span>
    </button>
  );
}

function RailButton({
  label,
  icon,
  active = false,
  onClick,
}: {
  label: string;
  icon: ReactNode;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className={`flex h-10 w-10 items-center justify-center rounded-full transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background ${
        active
          ? "bg-accent-soft text-accent"
          : "text-muted hover:bg-elevated hover:text-foreground"
      }`}
    >
      {icon}
    </button>
  );
}

interface UserInfo {
  email: string;
  name: string;
  initial: string;
}

function getUserInfo(user: ReturnType<typeof useAuth>["user"]): UserInfo {
  const email = user?.email ?? "usuario@correo.com";
  const name = user?.displayName ?? email.split("@")[0] ?? "Usuario";
  return {
    email,
    name,
    initial: name[0]?.toUpperCase() ?? "U",
  };
}

function PanelIcon() {
  return (
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
  );
}

function PlusIcon() {
  return (
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
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function SearchIcon() {
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
      className="shrink-0"
    >
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.35-4.35" />
    </svg>
  );
}

function PencilEditIcon() {
  return (
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
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}
