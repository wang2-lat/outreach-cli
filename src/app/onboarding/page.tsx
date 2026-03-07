"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  STATES,
  ENTITY_TYPES,
  INDUSTRIES,
  EMPLOYEE_COUNTS,
  EMPLOYMENT_TYPES,
  WORK_LOCATIONS,
  type BusinessInfo,
} from "@/lib/constants";
import { useBusiness } from "@/lib/business-context";

const STEPS = [
  {
    key: "state" as const,
    title: "Where is your business located?",
    subtitle: "We'll customize your compliance checklist for your state.",
    options: STATES,
  },
  {
    key: "entityType" as const,
    title: "What type of business entity are you?",
    subtitle: "Different entity types have different requirements.",
    options: ENTITY_TYPES,
  },
  {
    key: "industry" as const,
    title: "What industry are you in?",
    subtitle: "Some industries have additional compliance requirements.",
    options: INDUSTRIES,
  },
  {
    key: "employeeCount" as const,
    title: "How many employees do you plan to hire?",
    subtitle: "Certain regulations kick in at different employee thresholds.",
    options: EMPLOYEE_COUNTS,
  },
  {
    key: "employmentType" as const,
    title: "Full-time or part-time?",
    subtitle: "Benefits and requirements can differ based on employment type.",
    options: EMPLOYMENT_TYPES,
  },
  {
    key: "workLocation" as const,
    title: "Where will your employees work?",
    subtitle: "Remote work may involve multi-state compliance.",
    options: WORK_LOCATIONS,
  },
];

export default function OnboardingPage() {
  const [currentStep, setCurrentStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const router = useRouter();
  const { setBusiness } = useBusiness();

  const step = STEPS[currentStep];
  const progress = ((currentStep + 1) / STEPS.length) * 100;

  const handleSelect = (value: string) => {
    const updated = { ...answers, [step.key]: value };
    setAnswers(updated);

    if (currentStep < STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      setBusiness(updated as unknown as BusinessInfo);
      router.push("/dashboard");
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Progress bar */}
      <div className="w-full bg-secondary h-1.5">
        <div
          className="bg-primary h-1.5 transition-all duration-500 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Header */}
      <div className="px-4 py-4 flex items-center justify-between">
        <span className="text-lg font-bold text-primary">HireRight AI</span>
        <span className="text-sm text-muted-foreground">
          {currentStep + 1} of {STEPS.length}
        </span>
      </div>

      {/* Main content */}
      <div className="flex-1 flex items-center justify-center px-4 py-8">
        <div className="w-full max-w-lg text-center">
          <h1 className="text-2xl md:text-3xl font-bold text-foreground mb-2">
            {step.title}
          </h1>
          <p className="text-muted-foreground mb-10">{step.subtitle}</p>

          <div className="grid gap-3">
            {step.options.map((option) => (
              <button
                key={option.value}
                onClick={() => handleSelect(option.value)}
                className={`w-full rounded-xl border-2 px-6 py-4 text-left text-lg font-medium transition-all hover:border-primary hover:bg-primary/5 ${
                  answers[step.key] === option.value
                    ? "border-primary bg-primary/5"
                    : "border-border bg-card"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>

          {currentStep > 0 && (
            <button
              onClick={handleBack}
              className="mt-8 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              &larr; Back
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
