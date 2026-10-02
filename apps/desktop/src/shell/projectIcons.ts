import {
  BookOpen,
  Briefcase,
  Calendar,
  ChartLine,
  Code,
  Folder,
  GraduationCap,
  HeartPulse,
  House,
  ListChecks,
  Mail,
  Megaphone,
  NotebookPen,
  Plane,
  ShoppingCart,
  Sparkles,
  StickyNote,
  Target,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";

/** The icons a project may wear: Core's allowed list, kebab-case lucide names. */
export const PROJECT_ICONS: Record<string, LucideIcon> = {
  folder: Folder,
  briefcase: Briefcase,
  "notebook-pen": NotebookPen,
  calendar: Calendar,
  users: Users,
  "chart-line": ChartLine,
  mail: Mail,
  "list-checks": ListChecks,
  "graduation-cap": GraduationCap,
  "heart-pulse": HeartPulse,
  wallet: Wallet,
  "shopping-cart": ShoppingCart,
  plane: Plane,
  house: House,
  code: Code,
  megaphone: Megaphone,
  "book-open": BookOpen,
  sparkles: Sparkles,
  "sticky-note": StickyNote,
  target: Target,
};

export function projectIcon(name: string | null | undefined): LucideIcon {
  return (name && PROJECT_ICONS[name]) || Folder;
}
