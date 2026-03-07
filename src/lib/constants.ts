export const STATES = [
  { value: "california", label: "California" },
  { value: "texas", label: "Texas" },
] as const;

export const ENTITY_TYPES = [
  { value: "llc", label: "LLC" },
  { value: "c-corp", label: "C-Corp" },
  { value: "s-corp", label: "S-Corp" },
  { value: "sole-proprietorship", label: "Sole Proprietorship" },
] as const;

export const INDUSTRIES = [
  { value: "restaurant", label: "Restaurant / Food Service" },
  { value: "retail", label: "Retail" },
  { value: "tech", label: "Technology" },
  { value: "construction", label: "Construction" },
  { value: "professional-services", label: "Professional Services" },
  { value: "other", label: "Other" },
] as const;

export const EMPLOYEE_COUNTS = [
  { value: "1-5", label: "1-5 employees" },
  { value: "6-15", label: "6-15 employees" },
  { value: "16-50", label: "16-50 employees" },
] as const;

export const EMPLOYMENT_TYPES = [
  { value: "full-time", label: "Full-time" },
  { value: "part-time", label: "Part-time" },
  { value: "both", label: "Both" },
] as const;

export const WORK_LOCATIONS = [
  { value: "on-site", label: "On-site" },
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
] as const;

export type State = (typeof STATES)[number]["value"];
export type EntityType = (typeof ENTITY_TYPES)[number]["value"];
export type Industry = (typeof INDUSTRIES)[number]["value"];
export type EmployeeCount = (typeof EMPLOYEE_COUNTS)[number]["value"];
export type EmploymentType = (typeof EMPLOYMENT_TYPES)[number]["value"];
export type WorkLocation = (typeof WORK_LOCATIONS)[number]["value"];

export interface BusinessInfo {
  state: State;
  entityType: EntityType;
  industry: Industry;
  employeeCount: EmployeeCount;
  employmentType: EmploymentType;
  workLocation: WorkLocation;
}

export const DISCLAIMER_TEXT =
  "HireRight AI provides information for reference only and does not constitute legal advice. Employment laws vary by state and change frequently. Please consult a licensed attorney for legal advice specific to your situation.";
