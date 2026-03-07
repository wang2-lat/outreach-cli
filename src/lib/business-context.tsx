"use client";

import {
  createContext,
  useContext,
  useSyncExternalStore,
  useCallback,
  type ReactNode,
} from "react";
import type { BusinessInfo } from "./constants";

interface BusinessContextType {
  business: BusinessInfo | null;
  setBusiness: (info: BusinessInfo) => void;
  clearBusiness: () => void;
}

const BusinessContext = createContext<BusinessContextType>({
  business: null,
  setBusiness: () => {},
  clearBusiness: () => {},
});

const STORAGE_KEY = "hireright-business-info";

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

function getSnapshot(): string | null {
  return localStorage.getItem(STORAGE_KEY);
}

function getServerSnapshot(): string | null {
  return null;
}

export function BusinessProvider({ children }: { children: ReactNode }) {
  const raw = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  let business: BusinessInfo | null = null;
  if (raw) {
    try {
      business = JSON.parse(raw);
    } catch {}
  }

  const setBusiness = useCallback((info: BusinessInfo) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(info));
    emitChange();
  }, []);

  const clearBusiness = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    emitChange();
  }, []);

  return (
    <BusinessContext.Provider value={{ business, setBusiness, clearBusiness }}>
      {children}
    </BusinessContext.Provider>
  );
}

export function useBusiness() {
  return useContext(BusinessContext);
}
