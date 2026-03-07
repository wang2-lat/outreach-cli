"use client";

import { ExternalLink, Clock, AlertTriangle, Calendar } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChecklistItem as ChecklistItemType } from "@/lib/checklist-types";

interface ChecklistItemProps {
  item: ChecklistItemType;
  completed: boolean;
  onToggle: () => void;
  expanded: boolean;
  onToggleExpand: () => void;
}

export function ChecklistItem({
  item,
  completed,
  onToggle,
  expanded,
  onToggleExpand,
}: ChecklistItemProps) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-card transition-all",
        completed ? "border-border/50 opacity-60" : "border-border"
      )}
    >
      {/* Header row */}
      <div className="flex items-start gap-3 p-4">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggle();
          }}
          className={cn(
            "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border-2 transition-colors",
            completed
              ? "border-primary bg-primary text-white"
              : "border-border hover:border-primary"
          )}
        >
          {completed && (
            <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none">
              <path
                d="M2 6l3 3 5-5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </button>

        <button
          onClick={onToggleExpand}
          className="flex-1 text-left"
        >
          <h3
            className={cn(
              "font-medium leading-snug",
              completed && "line-through text-muted-foreground"
            )}
          >
            {item.title}
          </h3>
          <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
            {item.plainEnglish}
          </p>
        </button>

        <button
          onClick={onToggleExpand}
          className="shrink-0 mt-1 text-muted-foreground hover:text-foreground transition-colors"
        >
          <svg
            className={cn(
              "h-4 w-4 transition-transform",
              expanded && "rotate-180"
            )}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-border px-4 py-4 space-y-4">
          {/* Detailed description */}
          <div>
            <h4 className="text-sm font-medium text-foreground mb-1">Details</h4>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {item.description}
            </p>
          </div>

          {/* In plain English */}
          <div className="rounded-lg bg-primary/5 border border-primary/10 p-3">
            <h4 className="text-sm font-medium text-primary mb-1">
              In plain English
            </h4>
            <p className="text-sm text-foreground leading-relaxed">
              {item.plainEnglish}
            </p>
          </div>

          {/* Meta info grid */}
          <div className="grid gap-3 sm:grid-cols-2">
            {item.deadline && item.deadline !== "N/A" && (
              <div className="flex items-start gap-2">
                <Calendar className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Deadline</p>
                  <p className="text-sm text-foreground">{item.deadline}</p>
                </div>
              </div>
            )}
            {item.estimatedTime && item.estimatedTime !== "N/A" && (
              <div className="flex items-start gap-2">
                <Clock className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Estimated Time</p>
                  <p className="text-sm text-foreground">{item.estimatedTime}</p>
                </div>
              </div>
            )}
          </div>

          {/* Penalty warning */}
          {item.penalty && item.penalty !== "N/A" && (
            <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 p-3">
              <AlertTriangle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-medium text-red-600">If you don&apos;t comply</p>
                <p className="text-sm text-red-700">{item.penalty}</p>
              </div>
            </div>
          )}

          {/* Official link */}
          {item.officialUrl && (
            <a
              href={item.officialUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline font-medium"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Official government resource
            </a>
          )}
        </div>
      )}
    </div>
  );
}
