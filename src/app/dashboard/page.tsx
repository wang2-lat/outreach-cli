"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ClipboardList, Scale, FileText, MessageCircle, ArrowRight } from "lucide-react";
import { useBusiness } from "@/lib/business-context";
import { useChecklistProgress } from "@/lib/checklist-store";
import { ComplianceScore } from "@/components/ComplianceScore";
import { Disclaimer } from "@/components/Disclaimer";
import { Badge } from "@/components/ui/badge";
import type { ChecklistData, ChecklistItem } from "@/lib/checklist-types";

import federalData from "@/data/federal/checklist.json";
import californiaData from "@/data/california/checklist.json";
import texasData from "@/data/texas/checklist.json";

const stateDataMap: Record<string, ChecklistData> = {
  california: californiaData as ChecklistData,
  texas: texasData as ChecklistData,
};

function getAllItems(data: ChecklistData): ChecklistItem[] {
  return data.categories.flatMap((cat) => cat.items);
}

export default function DashboardPage() {
  const { business } = useBusiness();
  const { isCompleted, getCompletedCount } = useChecklistProgress();
  const router = useRouter();

  useEffect(() => {
    if (!business) {
      router.push("/onboarding");
    }
  }, [business, router]);

  if (!business) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  const stateData = stateDataMap[business.state];
  const federalItems = getAllItems(federalData as ChecklistData);
  const stateItems = stateData ? getAllItems(stateData) : [];
  const allItems = [...federalItems, ...stateItems];
  const allItemIds = allItems.map((i) => i.id);
  const completedCount = getCompletedCount(allItemIds);
  const totalCount = allItems.length;

  const incompleteItems = allItems.filter((item) => !isCompleted(item.id));
  const urgentItems = incompleteItems.filter((item) => item.deadline && !item.deadline.includes("N/A") && !item.deadline.includes("Ongoing"));
  const topItems = urgentItems.length > 0 ? urgentItems.slice(0, 3) : incompleteItems.slice(0, 3);

  const stateLabel = business.state === "california" ? "California" : "Texas";

  return (
    <div className="p-6 md:p-8 max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
        <p className="text-muted-foreground mt-1">
          Your compliance overview for hiring in {stateLabel}
        </p>
      </div>

      {/* Progress & Info */}
      <div className="grid gap-6 md:grid-cols-[200px_1fr]">
        <div className="flex justify-center md:justify-start">
          <ComplianceScore completed={completedCount} total={totalCount} />
        </div>
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Badge variant="secondary">{stateLabel}</Badge>
            <Badge variant="secondary">{business.entityType.toUpperCase()}</Badge>
            <Badge variant="secondary">{business.industry}</Badge>
            <Badge variant="secondary">{business.employeeCount} employees</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {completedCount === totalCount
              ? "Congratulations! You've completed all compliance items."
              : `You have ${totalCount - completedCount} items remaining. Start with the most urgent ones below.`}
          </p>
        </div>
      </div>

      {/* Priority Items */}
      {topItems.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold mb-4">Priority Items</h2>
          <div className="space-y-3">
            {topItems.map((item) => (
              <Link
                key={item.id}
                href="/dashboard/checklist"
                className="block rounded-xl border border-border bg-card p-4 hover:border-primary/50 hover:shadow-sm transition-all"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-medium text-foreground">{item.title}</h3>
                    <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                      {item.plainEnglish}
                    </p>
                    {item.deadline && !item.deadline.includes("N/A") && (
                      <p className="text-xs text-primary font-medium mt-2">
                        Deadline: {item.deadline}
                      </p>
                    )}
                  </div>
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground mt-1" />
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Quick Nav */}
      <div>
        <h2 className="text-lg font-semibold mb-4">Tools</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <NavCard
            href="/dashboard/checklist"
            icon={<ClipboardList className="h-6 w-6" />}
            title="Compliance Checklist"
            description="Interactive step-by-step compliance guide"
          />
          <NavCard
            href="/dashboard/classifier"
            icon={<Scale className="h-6 w-6" />}
            title="W-2 vs 1099 Classifier"
            description="Worker classification analyzer"
            comingSoon
          />
          <NavCard
            href="/dashboard/handbook"
            icon={<FileText className="h-6 w-6" />}
            title="Employee Handbook"
            description="Generate a state-compliant handbook"
            comingSoon
          />
          <NavCard
            href="/dashboard/chat"
            icon={<MessageCircle className="h-6 w-6" />}
            title="AI Compliance Chat"
            description="Ask labor law questions"
            comingSoon
          />
        </div>
      </div>

      <Disclaimer variant="banner" />
    </div>
  );
}

function NavCard({
  href,
  icon,
  title,
  description,
  comingSoon = false,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  description: string;
  comingSoon?: boolean;
}) {
  return (
    <Link
      href={href}
      className="flex items-start gap-4 rounded-xl border border-border bg-card p-5 hover:border-primary/50 hover:shadow-sm transition-all"
    >
      <div className="text-primary shrink-0">{icon}</div>
      <div>
        <div className="flex items-center gap-2">
          <h3 className="font-medium text-foreground">{title}</h3>
          {comingSoon && (
            <Badge variant="secondary" className="text-[10px]">
              Soon
            </Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground mt-1">{description}</p>
      </div>
    </Link>
  );
}
