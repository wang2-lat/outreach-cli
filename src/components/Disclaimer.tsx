"use client";

import { cn } from "@/lib/utils";
import { DISCLAIMER_TEXT } from "@/lib/constants";

interface DisclaimerProps {
  variant?: "inline" | "banner";
  className?: string;
}

export function Disclaimer({ variant = "inline", className }: DisclaimerProps) {
  if (variant === "banner") {
    return (
      <div
        className={cn(
          "rounded-lg border border-orange-200 bg-orange-50/50 px-4 py-3 text-sm text-muted-foreground",
          className
        )}
      >
        <p className="leading-relaxed">{DISCLAIMER_TEXT}</p>
      </div>
    );
  }

  return (
    <p
      className={cn(
        "text-xs text-muted-foreground/70 leading-relaxed",
        className
      )}
    >
      {DISCLAIMER_TEXT}
    </p>
  );
}
