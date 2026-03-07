"use client";

import { BusinessProvider } from "@/lib/business-context";
import type { ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
  return <BusinessProvider>{children}</BusinessProvider>;
}
