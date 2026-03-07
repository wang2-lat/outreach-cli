"use client";

import { useSyncExternalStore, useCallback } from "react";

const STORAGE_KEY = "hireright-checklist-progress";

interface ChecklistProgress {
  [itemId: string]: {
    completed: boolean;
    completedAt?: string;
    notes?: string;
  };
}

let listeners: Array<() => void> = [];

function emitChange() {
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners = [...listeners, listener];
  return () => {
    listeners = listeners.filter((l) => l !== listener);
  };
}

function getSnapshot(): string {
  return localStorage.getItem(STORAGE_KEY) || "{}";
}

function getServerSnapshot(): string {
  return "{}";
}

function getProgress(): ChecklistProgress {
  try {
    return JSON.parse(getSnapshot());
  } catch {
    return {};
  }
}

export function useChecklistProgress() {
  const raw = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  let progress: ChecklistProgress;
  try {
    progress = JSON.parse(raw);
  } catch {
    progress = {};
  }

  const toggleItem = useCallback((itemId: string) => {
    const current = getProgress();
    const updated = { ...current };
    if (updated[itemId]?.completed) {
      updated[itemId] = { completed: false };
    } else {
      updated[itemId] = {
        completed: true,
        completedAt: new Date().toISOString(),
      };
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    emitChange();
  }, []);

  const isCompleted = useCallback(
    (itemId: string) => {
      return progress[itemId]?.completed ?? false;
    },
    [progress]
  );

  const getCompletedCount = useCallback(
    (itemIds: string[]) => {
      return itemIds.filter((id) => progress[id]?.completed).length;
    },
    [progress]
  );

  const getProgressPercent = useCallback(
    (itemIds: string[]) => {
      if (itemIds.length === 0) return 0;
      const completed = getCompletedCount(itemIds);
      return Math.round((completed / itemIds.length) * 100);
    },
    [getCompletedCount]
  );

  return {
    progress,
    toggleItem,
    isCompleted,
    getCompletedCount,
    getProgress: getProgressPercent,
  };
}
