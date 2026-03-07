"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useBusiness } from "@/lib/business-context";
import { useChecklistProgress } from "@/lib/checklist-store";
import { ChecklistItem } from "@/components/ChecklistItem";
import { Disclaimer } from "@/components/Disclaimer";
import type {
  ChecklistData,
  ChecklistCategory,
  ChecklistItem as ChecklistItemType,
} from "@/lib/checklist-types";

import federalData from "@/data/federal/checklist.json";
import californiaData from "@/data/california/checklist.json";
import texasData from "@/data/texas/checklist.json";

const stateDataMap: Record<string, ChecklistData> = {
  california: californiaData as ChecklistData,
  texas: texasData as ChecklistData,
};

type FilterType = "all" | "incomplete" | "completed" | "urgent";

export default function ChecklistPage() {
  const { business } = useBusiness();
  const {
    toggleItem,
    isCompleted,
    getCompletedCount,
  } = useChecklistProgress();
  const router = useRouter();
  const [filter, setFilter] = useState<FilterType>("all");
  const [expandedItem, setExpandedItem] = useState<string | null>(null);

  useEffect(() => {
    if (!business) {
      router.push("/onboarding");
    }
  }, [business, router]);

  const categories = useMemo(() => {
    if (!business) return [];
    const stateData = stateDataMap[business.state];
    const federal = federalData as ChecklistData;
    const allCategories: Array<ChecklistCategory & { source: string }> = [];

    federal.categories.forEach((cat) => {
      allCategories.push({ ...cat, source: "Federal" });
    });

    if (stateData) {
      stateData.categories.forEach((cat) => {
        allCategories.push({ ...cat, source: stateData.state });
      });
    }

    return allCategories;
  }, [business]);

  const allItems = useMemo(
    () => categories.flatMap((cat) => cat.items),
    [categories]
  );

  const allItemIds = useMemo(() => allItems.map((i) => i.id), [allItems]);

  const filteredCategories = useMemo(() => {
    return categories
      .map((cat) => {
        const filteredItems = cat.items.filter((item) => {
          const completed = isCompleted(item.id);
          switch (filter) {
            case "incomplete":
              return !completed;
            case "completed":
              return completed;
            case "urgent":
              return (
                !completed &&
                item.deadline &&
                !item.deadline.includes("N/A") &&
                !item.deadline.includes("Ongoing")
              );
            default:
              return true;
          }
        });
        return { ...cat, items: filteredItems };
      })
      .filter((cat) => cat.items.length > 0);
  }, [categories, filter, isCompleted]);

  if (!business) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  const completedCount = getCompletedCount(allItemIds);
  const totalCount = allItems.length;
  const progressPercent =
    totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  const stateLabel = business.state === "california" ? "California" : "Texas";

  const filters: { key: FilterType; label: string }[] = [
    { key: "all", label: "All" },
    { key: "incomplete", label: "Incomplete" },
    { key: "completed", label: "Completed" },
    { key: "urgent", label: "Urgent" },
  ];

  return (
    <div className="p-6 md:p-8 max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">
          Compliance Checklist
        </h1>
        <p className="text-muted-foreground mt-1">
          Federal + {stateLabel} requirements for your first hire
        </p>
      </div>

      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            {completedCount} of {totalCount} completed
          </span>
          <span className="font-medium text-foreground">{progressPercent}%</span>
        </div>
        <div className="h-2 rounded-full bg-secondary">
          <div
            className="h-2 rounded-full bg-primary transition-all duration-500"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {filters.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              filter === f.key
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-muted-foreground hover:text-foreground"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Categories & Items */}
      {filteredCategories.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          {filter === "completed"
            ? "No completed items yet. Start checking off your list!"
            : filter === "urgent"
            ? "No urgent items with deadlines. Nice!"
            : "No items to show."}
        </div>
      ) : (
        <div className="space-y-8">
          {filteredCategories.map((category) => (
            <div key={category.id}>
              <div className="mb-3">
                <div className="flex items-center gap-2">
                  <h2 className="text-lg font-semibold text-foreground">
                    {category.title}
                  </h2>
                  <span className="text-xs text-muted-foreground bg-secondary px-2 py-0.5 rounded-full">
                    {category.source}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground">
                  {category.description}
                </p>
              </div>
              <div className="space-y-3">
                {category.items.map((item: ChecklistItemType) => (
                  <ChecklistItem
                    key={item.id}
                    item={item}
                    completed={isCompleted(item.id)}
                    onToggle={() => toggleItem(item.id)}
                    expanded={expandedItem === item.id}
                    onToggleExpand={() =>
                      setExpandedItem(
                        expandedItem === item.id ? null : item.id
                      )
                    }
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <Disclaimer variant="banner" className="mt-8" />
    </div>
  );
}
