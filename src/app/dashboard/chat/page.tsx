"use client";

import { MessageCircle } from "lucide-react";
import { Disclaimer } from "@/components/Disclaimer";

export default function ChatPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center">
      <div className="rounded-full bg-primary/10 p-4 mb-4">
        <MessageCircle className="h-8 w-8 text-primary" />
      </div>
      <h1 className="text-2xl font-bold text-foreground mb-2">
        AI Compliance Chat
      </h1>
      <p className="text-muted-foreground max-w-md mb-2">
        Ask labor law questions in plain English and get answers with legal
        references and official sources.
      </p>
      <p className="text-sm text-primary font-medium">Coming Soon</p>
      <Disclaimer variant="inline" className="mt-8 max-w-md" />
    </div>
  );
}
