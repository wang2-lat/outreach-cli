"use client";

import { cn } from "@/lib/utils";

interface StateSelectorProps {
  value?: string;
  onChange: (value: string) => void;
  className?: string;
}

const states = [
  { value: "california", label: "California", emoji: "🌴" },
  { value: "texas", label: "Texas", emoji: "⛳" },
];

export function StateSelector({
  value,
  onChange,
  className,
}: StateSelectorProps) {
  return (
    <div className={cn("grid grid-cols-2 gap-3", className)}>
      {states.map((state) => {
        const isSelected = value === state.value;
        return (
          <button
            key={state.value}
            type="button"
            onClick={() => onChange(state.value)}
            className={cn(
              "flex flex-col items-center gap-2 rounded-xl border-2 bg-card px-4 py-5 text-sm font-medium transition-all hover:shadow-md",
              isSelected
                ? "border-primary bg-primary/5 shadow-sm"
                : "border-border hover:border-primary/40"
            )}
          >
            <span className="text-3xl">{state.emoji}</span>
            <span
              className={cn(
                "font-semibold",
                isSelected ? "text-primary" : "text-foreground"
              )}
            >
              {state.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
