"use client";

import { useEffect, useState } from "react";
import {
  collection,
  onSnapshot,
  orderBy,
  query,
  where,
} from "firebase/firestore";
import { db } from "@/lib/firebase";
import { useAuth } from "@/components/providers/AuthProvider";

export interface Conversation {
  id: string;
  title: string;
  threadId: string;
  createdAt: Date;
  updatedAt: Date;
  messageCount: number;
}

export function useConversations(): {
  conversations: Conversation[];
  loading: boolean;
} {
  const { user } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!user) {
      setConversations([]);
      return;
    }

    setLoading(true);

    const q = query(
      collection(db, "conversations"),
      where("userId", "==", user.uid),
      orderBy("updatedAt", "desc")
    );

    const unsubscribe = onSnapshot(
      q,
      (snapshot) => {
        const convs: Conversation[] = snapshot.docs.map((docSnap) => {
          const data = docSnap.data();
          return {
            id: docSnap.id,
            title: (data.title as string) ?? "Sin título",
            threadId: (data.threadId as string) ?? "",
            createdAt: data.createdAt?.toDate?.() ?? new Date(),
            updatedAt: data.updatedAt?.toDate?.() ?? new Date(),
            messageCount: (data.messageCount as number) ?? 0,
          };
        });
        setConversations(convs);
        setLoading(false);
      },
      (err) => {
        console.error("[useConversations] Error en onSnapshot:", err);
        setLoading(false);
      }
    );

    return unsubscribe;
  }, [user]);

  return { conversations, loading };
}
