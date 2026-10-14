// Shapes returned by the FastAPI backend (see backend/src/*/schemas.py).
// Decimal fields arrive as strings, enums keep the backend spelling.

export type CurrencyCode =
  | 'USD' | 'EUR' | 'JPY' | 'GBP' | 'AUD' | 'CHF' | 'SEK' | 'NOK' | 'PLN' | 'UAH';

export const CURRENCIES: CurrencyCode[] = [
  'UAH', 'USD', 'EUR', 'GBP', 'PLN', 'CHF', 'JPY', 'AUD', 'SEK', 'NOK',
];

/** Backend TransactionKind enum values */
export const TxKind = { EXPENSE: 0, INCOME: 1, TRANSFER: 2 } as const;
export type TxKindValue = (typeof TxKind)[keyof typeof TxKind];

export type SubscriptionPlan = 'FREE' | 'PRO';

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface LoginResponse {
  access_token: string | null;
  refresh_token: string | null;
  token_type: string;
  requires_2fa: boolean;
  temp_token: string | null;
}

export interface UserOut {
  id_: number;
  username: string;
  email: string;
  default_currency: CurrencyCode;
  timezone: string | null;
  capital: number;
  role: number;
  avatar_url: string | null;
  twofa_enabled: boolean;
  subscription_plan: SubscriptionPlan;
}

export interface TransactionOut {
  id_: number;
  name: string;
  amount: string;
  kind: TxKindValue;
  category_name: string;
  currency: string | null;
  date: string;
  tags: string[];
  note: string | null;
  new_capital: number | null;
}

export interface TransactionInput {
  name: string;
  amount: number;
  kind: TxKindValue;
  category_name: string;
  currency?: string;
  date?: string;
  tags?: string[];
  note?: string | null;
}

export interface CategoriesList {
  expense: string[];
  income: string[];
  transfer: string[];
}

export type RecurringFrequency = 'DAILY' | 'WEEKLY' | 'BIWEEKLY' | 'MONTHLY' | 'YEARLY';

export interface RecurringOut {
  id_: number;
  user_id: number;
  name: string;
  amount: string;
  kind: TxKindValue;
  category_name: string;
  currency: string | null;
  tags: string[];
  note: string | null;
  frequency: RecurringFrequency;
  next_run: string;
  is_active: boolean;
  created_at: string;
}

export interface RecurringInput {
  name: string;
  amount: number;
  kind: TxKindValue;
  category_name: string;
  currency?: string;
  tags?: string[];
  note?: string | null;
  frequency: RecurringFrequency;
  first_run: string;
}

export interface ImportResult {
  imported: number;
  skipped: number;
  errors: string[];
  new_capital: number;
}

export type BudgetType = 'PERSONAL' | 'FAMILY' | 'BUSINESS';
export type BudgetRole = 'OWNER' | 'EDITOR' | 'VIEWER';

export interface BudgetOut {
  id_: number;
  owner_user_id: number;
  name: string;
  type: BudgetType;
  currency: CurrencyCode;
  limit_amount: string | null;
}

export interface BudgetMemberOut {
  id_: number;
  budget_id: number;
  user_id: number;
  role: BudgetRole;
  username: string | null;
  email: string | null;
}

export interface GoalOut {
  id_: number;
  user_id: number;
  name: string;
  target_amount: string;
  saved_amount: string;
  currency: CurrencyCode;
  description: string | null;
  deadline: string | null;
  is_completed: boolean;
  completed_at: string | null;
  created_at: string;
  progress_percent: number;
}

export interface OverviewOut {
  balance: number;
  total_income: number;
  total_expenses: number;
  net: number;
  currency: string;
}

export interface MonthlyPoint {
  year: number;
  month: number;
  income: number;
  expenses: number;
  net: number;
}

export interface MonthlyTrendsOut {
  months: MonthlyPoint[];
  currency: string;
}

export interface CategoryItem {
  category: string;
  amount: number;
  percent: number;
  count: number;
}

export interface CategoryBreakdownOut {
  kind: string;
  total: number;
  items: CategoryItem[];
  currency: string;
}

export interface PeriodSnapshot {
  from_: string;
  to: string;
  income: number;
  expenses: number;
  net: number;
  transaction_count: number;
}

export interface PeriodComparisonOut {
  current: PeriodSnapshot;
  previous: PeriodSnapshot;
  change: {
    income_diff: number;
    income_pct: number | null;
    expenses_diff: number;
    expenses_pct: number | null;
    net_diff: number;
    net_pct: number | null;
  };
  currency: string;
}

export interface BudgetComparisonOut {
  budget_id: number;
  budget_name: string;
  budget_type: BudgetType;
  limit_amount: number | null;
  actual_spent: number;
  remaining: number | null;
  utilization_percent: number | null;
  by_category: { category: string; amount: number }[];
  currency: string;
}

export interface NotificationPreferences {
  email_enabled: boolean;
  push_enabled: boolean;
  budget_limit_alerts: boolean;
  recurring_reminders: boolean;
  goal_milestone_alerts: boolean;
  monthly_summary: boolean;
}

export interface SubscriptionOut {
  plan: SubscriptionPlan;
  features: { label: string; available: boolean }[];
}

export interface TwoFASetup {
  qr_code_base64: string;
  secret: string;
}
