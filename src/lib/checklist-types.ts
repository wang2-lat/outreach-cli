export interface ChecklistItem {
  id: string;
  title: string;
  description: string;
  plainEnglish: string;
  deadline: string;
  penalty: string;
  estimatedTime: string;
  officialUrl: string;
  requiredFor: string[];
  dependsOn: string[];
}

export interface ChecklistCategory {
  id: string;
  title: string;
  description: string;
  items: ChecklistItem[];
}

export interface ChecklistData {
  state: string;
  lastUpdated: string;
  categories: ChecklistCategory[];
}
