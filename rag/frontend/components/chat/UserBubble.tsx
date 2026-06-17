"use client";

import { motion } from "motion/react";

interface UserBubbleProps {
	text: string;
}

export function UserBubble({ text }: UserBubbleProps) {
	return (
		<motion.div
			className="flex justify-end"
			initial={{ opacity: 0, y: 8, x: 6 }}
			animate={{ opacity: 1, y: 0, x: 0 }}
			transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
		>
			<div className="max-w-[72%] min-w-0 break-words rounded-3xl rounded-tr-md border border-border bg-elevated px-4 py-2.5 text-[15px] leading-relaxed text-foreground">
				{text}
			</div>
		</motion.div>
	);
}
