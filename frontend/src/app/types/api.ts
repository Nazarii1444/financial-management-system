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

export interface TemplateOut {
  id_: number;
  name: string;
  amount: string;
  kind: TxKindValue;
  category_name: string;
  currency: string;
  tags: string[];
  note: string | null;
  use_count: number;
  last_used_at: string | null;
  created_at: string;
}

export interface TemplateInput {
  name: string;
  amount: number;
  kind: TxKindValue;
  category_name: string;
  currency?: string;
  tags?: string[];
  note?: string | null;
}

export interface TemplateUseInput {
  amount?: number;
  remember_amount?: boolean;
}

export interface TemplateSuggestion {
  key: string;
  name: string;
  amount: string;
  kind: TxKindValue;
  category_name: string;
  currency: string;
  count: number;
  min_amount: string;
  max_amount: string;
  last_date: string;
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

export interface SafeToSpendGoal {
  goal_id: number;
  name: string;
  saved: number;
  monthly_contribution: number;
  deadline: string | null;
}

export interface SafeToSpendOut {
  safe_to_spend_per_day: number;
  available_to_spend: number;
  balance: number;
  expected_income: number;
  upcoming_expenses: number;
  spent_this_month: number;
  goal_reserved: number;
  goal_contributions: number;
  goals: SafeToSpendGoal[];
  spent_today: number;
  daily_limit: number;
  left_today: number;
  per_day_after_today: number;
  days_remaining: number;
  month_end: string;
  currency: string;
  as_of: string;
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

export interface CalendarFeedOut {
  active: boolean;
  url: string | null;
  webcal_url: string | null;
  google_add_url: string | null;
  qr_code_base64: string | null;
  lang: string | null;
  created_at: string | null;
}

export interface GoogleCalendarStatus {
  configured: boolean;
  connected: boolean;
  calendar_id: string | null;
  calendar_url: string | null;
  last_synced_at: string | null;
  last_error: string | null;
}

export interface TransactionSearchItem extends TransactionOut {
  has_receipt: boolean;
}

export interface TransactionSearchOut {
  items: TransactionSearchItem[];
  total: number;
  totals: { expense: number; income: number; net: number; currency: string };
}

export interface TransactionDeletedOut extends TransactionOut {
  message: string;
  trash_id: number;
  expires_at: string;
}

export interface TrashItem {
  id_: number;
  transaction_id: number;
  name: string;
  amount: string;
  kind: TxKindValue;
  category_name: string;
  currency: string | null;
  date: string | null;
  tags: string[];
  note: string | null;
  has_receipt: boolean;
  deleted_at: string;
  expires_at: string;
}

export interface RecurringCostRow {
  id_: number;
  name: string;
  category: string;
  frequency: RecurringFrequency;
  amount: string;
  currency: string;
  per_month: string;
  per_year: string;
  next_run: string;
  subscription: boolean;
}

export interface RecurringSummary {
  currency: string;
  expenses: RecurringCostRow[];
  incomes: RecurringCostRow[];
  expense_per_month: string;
  expense_per_year: string;
  subscriptions_per_month: string;
  subscriptions_per_year: string;
  subscriptions_count: number;
  income_per_year: string;
  income_share: number | null;
}

export interface StatementPreviewRow {
  ref: string | null;
  date: string | null;
  name: string;
  description: string;
  amount: string;
  currency: string;
  kind: TxKindValue;
  category_name: string;
  note: string | null;
  tags: string[];
  mcc: string | null;
  balance_after: string | null;
  duplicate: boolean;
  similar: boolean;
  selected: boolean;
}

export interface StatementPreview {
  bank: string;
  bank_name: string;
  file_format: string;
  currency: string | null;
  period_from: string | null;
  period_to: string | null;
  opening_balance: string | null;
  closing_balance: string | null;
  rows: StatementPreviewRow[];
  warnings: string[];
}

export interface StatementImportRow {
  ref: string | null;
  date: string;
  name: string;
  amount: number;
  currency: string;
  kind: TxKindValue;
  category_name: string;
  note: string | null;
  tags: string[];
}

export interface StatementImportResult {
  imported: number;
  skipped_duplicates: number;
  errors: string[];
  new_capital: number;
}

// ── Security (Settings → Security) ───────────────────────────────────────────

export interface SecurityEvent {
  id_: number;
  /** login | twofa_challenge | signup | logout | password_changed | email_changed | twofa_enabled | twofa_disabled | passkey_added | passkey_removed | data_exported */
  event_type: string;
  success: boolean;
  /** password | totp | passkey | google | github */
  method: string | null;
  ip: string | null;
  device: string | null;
  device_type: 'mobile' | 'desktop' | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface SecurityEvents {
  items: SecurityEvent[];
  total: number;
  failed_last_30_days: number;
}

export type PasswordRecommendation =
  | 'change_breached'
  | 'change_weak'
  | 'password_old'
  | 'run_check'
  | 'enable_2fa_or_passkey'
  | 'add_passkey';

export interface PasswordHealth {
  changed_at: string | null;
  age_days: number | null;
  score: number | null;
  breached: boolean | null;
  checked_at: string | null;
  twofa_enabled: boolean;
  passkeys: number;
  level: 'good' | 'fair' | 'weak';
  recommendations: PasswordRecommendation[];
}

export interface PasswordStrength {
  score: number;
  acceptable: boolean;
  /** too_short | too_long | personal | common | weak */
  codes: string[];
  errors: string[];
  warning: string | null;
  suggestions: string[];
  crack_time: string | null;
  min_length: number;
}

export interface Passkey {
  id_: number;
  name: string;
  created_at: string;
  last_used_at: string | null;
  backed_up: boolean;
  transports: string[] | null;
}

export interface PasskeyOptions {
  challenge_id: string;
  public_key: Record<string, unknown>;
}
