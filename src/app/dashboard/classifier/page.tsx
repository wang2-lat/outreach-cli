"use client";

import { Scale } from "lucide-react";
import { Disclaimer } from "@/components/Disclaimer";

export default function ClassifierPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center">
      <div className="rounded-full bg-primary/10 p-4 mb-4">
        <Scale className="h-8 w-8 text-primary" />
      </div>
      <h1 className="text-2xl font-bold text-foreground mb-2">
        W-2 vs 1099 Classifier
      </h1>
      <p className="text-muted-foreground max-w-md mb-2">
        Answer a few questions to find out if your worker should be classified as
        a W-2 employee or 1099 independent contractor.
      </p>
      <p className="text-sm text-primary font-medium">Coming Soon</p>
      <Disclaimer variant="inline" className="mt-8 max-w-md" />
    </div>
  );
}
