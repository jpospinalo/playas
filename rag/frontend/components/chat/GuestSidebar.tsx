"use client";

import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import {
  AtlasGlyph,
  InfoIcon,
  PanelIcon,
  PencilEditIcon,
  RailButton,
  SidebarPillButton,
} from "@/components/chat/ConversationSidebar";
import {
  SIDEBAR_COLLAPSED_WIDTH,
  SIDEBAR_EXPANDED_WIDTH,
  SIDEBAR_TRANSITION,
} from "@/components/chat/conversationSidebarUtils";

interface GuestSidebarProps {
  isExpanded: boolean;
  transitionEnabled: boolean;
  onNewChat: () => void;
  onOpenAuth: () => void;
  onToggleSidebar: () => void;
}

function UserPlusIcon({ size = 16 }: { size?: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0"
    >
      <circle cx="9" cy="7" r="4" />
      <path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" />
      <path d="M16 11h6" />
      <path d="M19 8v6" />
    </svg>
  );
}

/** Sidebar reducido para visitantes sin sesión que ya iniciaron una conversación. */
export function GuestSidebar({
  isExpanded,
  transitionEnabled,
  onNewChat,
  onOpenAuth,
  onToggleSidebar,
}: GuestSidebarProps) {
  const router = useRouter();

  return (
    <>
      {isExpanded && (
        <div
          className="fixed inset-0 z-30 bg-foreground/20 md:hidden"
          onClick={onToggleSidebar}
          aria-hidden="true"
        />
      )}

      <motion.aside
        className={`hidden flex-none overflow-visible md:flex md:flex-col ${
          isExpanded
            ? "border-r border-border bg-elevated/60 backdrop-blur-md"
            : "bg-transparent"
        }`}
        initial={false}
        animate={{
          width: isExpanded ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_COLLAPSED_WIDTH,
        }}
        transition={transitionEnabled ? SIDEBAR_TRANSITION : { duration: 0 }}
      >
        <div className="flex h-full w-full flex-col overflow-hidden">
          <AnimatePresence initial={false} mode="wait">
            {isExpanded ? (
              <motion.div
                key="expanded"
                initial={transitionEnabled ? { opacity: 0 } : false}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: transitionEnabled ? 0.12 : 0 }}
              >
                <div className="flex h-14 items-center justify-between px-5">
                  <div className="flex items-center gap-2.5">
                    <AtlasGlyph />
                    <span
                      className="text-base font-medium tracking-[0.04em] text-foreground"
                      translate="no"
                    >
                      ATLAS
                    </span>
                  </div>
                  <button
                    onClick={onToggleSidebar}
                    aria-label="Cerrar panel"
                    title="Cerrar panel"
                    className="flex h-9 w-9 items-center justify-center rounded-full text-muted transition-colors hover:bg-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  >
                    <PanelIcon />
                  </button>
                </div>

                <div className="px-3 pt-2">
                  <SidebarPillButton
                    label="Nueva consulta"
                    icon={<PencilEditIcon />}
                    emphasis="primary"
                    onClick={onNewChat}
                  />
                  <SidebarPillButton
                    label="Cómo funciona"
                    icon={<InfoIcon />}
                    onClick={() => router.push("/about")}
                  />
                  <SidebarPillButton
                    label="Iniciar sesión"
                    icon={<UserPlusIcon size={18} />}
                    onClick={onOpenAuth}
                  />
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="collapsed"
                className="flex h-full flex-col items-center gap-2 px-2 pt-3"
                initial={transitionEnabled ? { opacity: 0 } : false}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: transitionEnabled ? 0.12 : 0 }}
              >
                <button
                  type="button"
                  onClick={onToggleSidebar}
                  aria-label="Abrir panel"
                  title="Abrir panel"
                  className="group/atlas relative mb-2 flex h-12 w-12 items-center justify-center rounded-full text-foreground transition-colors duration-150 hover:bg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  <span className="absolute inset-0 flex items-center justify-center transition-opacity duration-150 group-hover/atlas:opacity-0 group-focus-visible/atlas:opacity-0">
                    <AtlasGlyph />
                  </span>
                  <span className="absolute inset-0 flex items-center justify-center text-muted opacity-0 transition-opacity duration-150 group-hover/atlas:opacity-100 group-hover/atlas:text-foreground group-focus-visible/atlas:opacity-100 group-focus-visible/atlas:text-foreground">
                    <PanelIcon />
                  </span>
                </button>
                <RailButton label="Nueva consulta" icon={<PencilEditIcon />} onClick={onNewChat} />
                <RailButton
                  label="Cómo funciona"
                  icon={<InfoIcon />}
                  onClick={() => router.push("/about")}
                />
                <RailButton
                  label="Iniciar sesión"
                  icon={<UserPlusIcon />}
                  onClick={onOpenAuth}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.aside>
    </>
  );
}
