"use client";

import { cn } from "@/lib/utils";

interface ComplianceScoreProps {
  completed: number;
  total: number;
  className?: string;
}

export function ComplianceScore({
  completed,
  total,
  className,
}: ComplianceScoreProps) {
  const percentage = total > 0 ? Math.round((completed / total) * 100) : 0;
  const radius = 50;
  const strokeWidth = 8;
  const normalizedRadius = radius - strokeWidth / 2;
  const circumference = 2 * Math.PI * normalizedRadius;
  const strokeDashoffset = circumference - (percentage / 100) * circumference;

  return (
    <div className={cn("flex flex-col items-center gap-2", className)}>
      <div className="relative" style={{ width: 120, height: 120 }}>
        <svg
          width="120"
          height="120"
          viewBox="0 0 100 100"
          className="-rotate-90"
        >
          {/* Background track */}
          <circle
            cx="50"
            cy="50"
            r={normalizedRadius}
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            className="text-muted/30"
          />
          {/* Progress ring */}
          <circle
            cx="50"
            cy="50"
            r={normalizedRadius}
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            className="text-primary transition-all duration-500 ease-in-out"
          />
        </svg>
        {/* Center text */}
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-2xl font-bold text-foreground">
            {percentage}%
          </span>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">
        {completed} of {total} completed
      </p>
    </div>
  );
}
