"use client";

import { motion } from "motion/react";

interface UserBubbleProps {
  text: string;
}

export function UserBubble({ text }: UserBubbleProps) {
  return (
    <motion.div
      className="flex justify-end"
      initial={{ opacity: 0, y: 10, x: 8 }}
      animate={{ opacity: 1, y: 0, x: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="max-w-[68%] min-w-0 break-words rounded-2xl rounded-tr-sm bg-navy px-4 py-3 text-sm leading-relaxed text-white shadow-sm">
        {text}
      </div>
    </motion.div>
  );
}
