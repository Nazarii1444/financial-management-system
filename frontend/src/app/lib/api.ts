import type {
  Passkey,
  PasskeyOptions,
  PasswordHealth,
  PasswordStrength,
  SecurityEvents,
  BudgetComparisonOut,
  BudgetMemberOut,
  BudgetOut,
  BudgetRole,
  BudgetType,
  CategoriesList,
  CalendarFeedOut,
  CategoryBreakdownOut,
  GoalOut,
  GoogleCalendarStatus,
  ImportResult,
  LoginResponse,
  MonthlyTrendsOut,
  NotificationPreferences,
  OverviewOut,
  PeriodComparisonOut,
  RecurringInput,
  RecurringOut,
  RecurringSummary,
  SafeToSpendOut,
  StatementImportResult,
  StatementImportRow,
  StatementPreview,
  SubscriptionOut,
  TemplateInput,
  TemplateOut,
  TemplateSuggestion,
  TemplateUseInput,
  TokenPair,
  TransactionInput,
  TransactionDeletedOut,
  TransactionOut,
  TransactionSearchOut,
  TrashItem,
  TwoFASetup,
  TxKindValue,
  UserOut,
} from '../types/api';

// In dev, Vite proxies /api to the backend (see vite.config.ts).
// Set VITE_API_URL to call a backend on another origin instead.
const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') || '/api';

// OAuth must be a real browser navigation straight to the backend (not via the
// dev proxy), so the OAuth state cookie lives on the same host as the callback.
const BACKEND_URL = ((import.meta.env.VITE_BACKEND_URL as string | undefined) || 'http://127.0.0.1:8000').replace(/\/$/, '');
export const oauthLoginUrl = (provider: 'google' | 'github') => `${BACKEND_URL}/api/auth/${provider}/login`;

// ── Errors ───────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

// ── Token storage ────────────────────────────────────────────────────────────
// "Remember me" keeps tokens in localStorage; otherwise they live for the tab session.

const TOKENS_KEY = 'fms.tokens';

interface StoredTokens {
  access: string;
  refresh: string;
}

function readStore(storage: Storage): StoredTokens | null {
  try {
    const raw = storage.getItem(TOKENS_KEY);
    return raw ? (JSON.parse(raw) as StoredTokens) : null;
  } catch {
    return null;
  }
}

export const tokenStore = {
  get(): StoredTokens | null {
    return readStore(localStorage) ?? readStore(sessionStorage);
  },
  set(tokens: StoredTokens, remember?: boolean) {
    // Keep the current storage when rotating tokens after a refresh
    const persistent = remember ?? readStore(localStorage) !== null;
    try {
      this.clear();
      (persistent ? localStorage : sessionStorage).setItem(TOKENS_KEY, JSON.stringify(tokens));
    } catch {
      // Storage unavailable — the session just won't survive a reload
    }
  },
  clear() {
    try {
      localStorage.removeItem(TOKENS_KEY);
      sessionStorage.removeItem(TOKENS_KEY);
    } catch {
      // ignore
    }
  },
};

/** Fired when the session can no longer be refreshed; AuthContext listens to it. */
export const SESSION_EXPIRED_EVENT = 'fms:session-expired';

// ── Core request ─────────────────────────────────────────────────────────────

type Query = Record<string, string | number | boolean | null | undefined>;

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Query;
  auth?: boolean;
}

function buildUrl(path: string, query?: Query) {
  const url = `${API_URL}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') params.append(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

let refreshInFlight: Promise<boolean> | null = null;

async function refreshTokens(): Promise<boolean> {
  const tokens = tokenStore.get();
  if (!tokens?.refresh) return false;
  refreshInFlight ??= (async () => {
    try {
      const res = await fetch(buildUrl('/auth/refresh'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: tokens.refresh }),
      });
      if (!res.ok) return false;
      const pair = (await res.json()) as TokenPair;
      tokenStore.set({ access: pair.access_token, refresh: pair.refresh_token });
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function parseBody(res: Response) {
  if (res.status === 204) return undefined;
  const text = await res.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function request<T>(path: string, options: RequestOptions = {}, retried = false): Promise<T> {
  const { method = 'GET', body, query, auth = true } = options;
  const headers: Record<string, string> = {};
  const isForm = body instanceof FormData;
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';
  if (auth) {
    const access = tokenStore.get()?.access;
    if (access) headers.Authorization = `Bearer ${access}`;
  }

  let res: Response;
  try {
    res = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'Network error');
  }

  if (res.status === 401 && auth && !retried) {
    if (await refreshTokens()) return request<T>(path, options, true);
    tokenStore.clear();
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
  }

  const data = await parseBody(res);
  if (!res.ok) {
    const detail = data && typeof data === 'object' && 'detail' in data ? (data as { detail: unknown }).detail : data;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

/** Authenticated file download (PDF / CSV); saves it with the server-provided filename. */
export async function downloadFile(path: string, query?: Query, headers: Record<string, string> = {}, retried = false): Promise<void> {
  const access = tokenStore.get()?.access;
  let res: Response;
  try {
    res = await fetch(buildUrl(path, query), { headers: { ...headers, ...(access ? { Authorization: `Bearer ${access}` } : {}) } });
  } catch {
    throw new ApiError(0, 'Network error');
  }
  if (res.status === 401 && !retried && (await refreshTokens())) return downloadFile(path, query, headers, true);
  if (!res.ok) {
    const data = await parseBody(res);
    const detail = data && typeof data === 'object' && 'detail' in data ? (data as { detail: unknown }).detail : data;
    throw new ApiError(res.status, detail);
  }
  const disposition = res.headers.get('Content-Disposition') ?? '';
  const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? 'download';
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const get = <T>(path: string, query?: Query) => request<T>(path, { query });
const post = <T>(path: string, body?: unknown, query?: Query) => request<T>(path, { method: 'POST', body, query });
const patch = <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body });
const del = <T = void>(path: string) => request<T>(path, { method: 'DELETE' });

// ── Endpoints ────────────────────────────────────────────────────────────────

export const authApi = {
  login: (email: string, password: string) =>
    request<LoginResponse>('/auth/login', { method: 'POST', body: { email, password }, auth: false }),
  signup: (username: string, email: string, password: string) =>
    request<LoginResponse>('/auth/signup', { method: 'POST', body: { username, email, password }, auth: false }),
  complete2fa: (temp_token: string, code: string) =>
    request<TokenPair>('/auth/2fa/complete', { method: 'POST', body: { temp_token, code }, auth: false }),
  logout: () => post<{ message: string }>('/auth/logout'),
  changePassword: (current_password: string, new_password: string) =>
    patch<{ message: string }>('/auth/password', { current_password, new_password }),
  // Not implemented on the backend yet — see docs/INTEGRATION_GAPS.md
  requestPasswordReset: (email: string) =>
    request<void>('/auth/password-reset/request', { method: 'POST', body: { email }, auth: false }),
  verifyPasswordReset: (email: string, code: string) =>
    request<void>('/auth/password-reset/verify', { method: 'POST', body: { email, code }, auth: false }),
  confirmPasswordReset: (email: string, code: string, new_password: string) =>
    request<void>('/auth/password-reset/confirm', { method: 'POST', body: { email, code, new_password }, auth: false }),
};

export const usersApi = {
  me: () => get<UserOut>('/users/me'),
  deleteMe: () => del('/users/me'),
};

export interface TransactionFilters {
  limit?: number;
  offset?: number;
  kind?: TxKindValue;
  category?: string;
  tags?: string;
  date_from?: string;
  date_to?: string;
}

/** Filters of GET /transactions/search (also accepted by the CSV export) */
export interface SearchFilters {
  q?: string;
  kind?: TxKindValue;
  category?: string;
  tags?: string;
  date_from?: string;
  date_to?: string;
  amount_min?: number;
  amount_max?: number;
  currency?: string;
  has_receipt?: boolean;
}

export const transactionsApi = {
  list: (filters: TransactionFilters = {}) => get<TransactionOut[]>('/transactions', { ...filters }),
  create: (input: TransactionInput) => post<TransactionOut>('/transactions', input),
  update: (id: number, input: Partial<TransactionInput>) => patch<TransactionOut>(`/transactions/${id}`, input),
  /** Moves to the trash; restore with trashApi.restore(result.trash_id) */
  remove: (id: number) => del<TransactionDeletedOut>(`/transactions/${id}`),
  search: (filters: SearchFilters & { limit?: number; offset?: number }) =>
    get<TransactionSearchOut>('/transactions/search', { ...filters }),
  categories: () => get<CategoriesList>('/transactions/categories/list'),
  import: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return post<ImportResult>('/transactions/import', form);
  },
  /** Bank statement (monobank PDF / CSV / XLSX) or app CSV / XLSX → reviewable rows; nothing is saved */
  previewStatement: (file: File, passphrase?: string) => {
    const form = new FormData();
    form.append('file', file);
    // Encrypted exports (.fhx): a form field, never the URL
    if (passphrase) form.append('passphrase', passphrase);
    return post<StatementPreview>('/transactions/import/statement/preview', form);
  },
  confirmStatement: (input: { bank: string; update_balance: boolean; rows: StatementImportRow[] }) =>
    post<StatementImportResult>('/transactions/import/statement/confirm', input),
};

export const trashApi = {
  list: () => get<TrashItem[]>('/transactions/trash'),
  restore: (id: number) => post<TransactionOut>(`/transactions/trash/${id}/restore`),
  purge: (id: number) => del(`/transactions/trash/${id}`),
  empty: () => del('/transactions/trash'),
};

/**
 * Optional export passphrase → request header (never the URL, so it stays out of logs and history).
 * Percent-encoded: header values are Latin-1 and passphrases may be Cyrillic.
 */
const passphraseHeader = (passphrase?: string): Record<string, string> =>
  passphrase ? { 'X-Export-Passphrase': encodeURIComponent(passphrase) } : {};

export const exportsApi = {
  transactionsCsv: (filters: SearchFilters, lang: string, passphrase?: string) =>
    downloadFile('/exports/transactions.csv', { ...filters, lang }, passphraseHeader(passphrase)),
  statementPdf: (month: string, lang: string, passphrase?: string) =>
    downloadFile('/exports/reports/statement.pdf', { month, lang }, passphraseHeader(passphrase)),
  expensesPdf: (month: string, lang: string, passphrase?: string) =>
    downloadFile('/exports/reports/expenses.pdf', { month, lang }, passphraseHeader(passphrase)),
  budgetsPdf: (month: string, lang: string, passphrase?: string) =>
    downloadFile('/exports/reports/budgets.pdf', { month, lang }, passphraseHeader(passphrase)),
  recurringPdf: (lang: string, passphrase?: string) =>
    downloadFile('/exports/reports/recurring.pdf', { lang }, passphraseHeader(passphrase)),
  recurringSummary: () => get<RecurringSummary>('/exports/reports/recurring'),
};

export const recurringApi = {
  list: () => get<RecurringOut[]>('/transactions/recurring', { limit: 200 }),
  create: (input: RecurringInput) => post<RecurringOut>('/transactions/recurring', input),
  update: (id: number, input: Partial<RecurringInput> & { is_active?: boolean }) =>
    patch<RecurringOut>(`/transactions/recurring/${id}`, input),
  remove: (id: number) => del(`/transactions/recurring/${id}`),
};

export const templatesApi = {
  list: () => get<TemplateOut[]>('/templates'),
  create: (input: TemplateInput) => post<TemplateOut>('/templates', input),
  update: (id: number, input: Partial<TemplateInput>) => patch<TemplateOut>(`/templates/${id}`, input),
  remove: (id: number) => del(`/templates/${id}`),
  /** Creates a transaction dated now; returns it with new_capital */
  use: (id: number, input: TemplateUseInput = {}) => post<TransactionOut>(`/templates/${id}/use`, input),
  suggestions: () => get<TemplateSuggestion[]>('/templates/suggestions'),
  dismissSuggestion: (key: string) => post<void>('/templates/suggestions/dismiss', { key }),
};

export const calendarApi = {
  /** .ics text of all active recurring rules (one-off snapshot) */
  downloadIcs: (lang: string) => get<string>('/calendar/recurring.ics', { lang }),
  feed: () => get<CalendarFeedOut>('/calendar/feed'),
  createFeed: (lang: string, rotate = false) => post<CalendarFeedOut>('/calendar/feed', undefined, { lang, rotate }),
  revokeFeed: () => del('/calendar/feed'),
  googleStatus: () => get<GoogleCalendarStatus>('/calendar/google/status'),
  googleConnect: (lang: string) => post<{ auth_url: string }>('/calendar/google/connect', undefined, { lang }),
  googleSync: () => post<{ synced: number; deleted: number; last_synced_at: string | null }>('/calendar/google/sync'),
  googleDisconnect: () => del('/calendar/google'),
};

export interface BudgetInput {
  name: string;
  type: BudgetType;
  currency: string;
  limit_amount?: number | null;
}

export const budgetsApi = {
  list: () => get<BudgetOut[]>('/budgets', { limit: 200 }),
  create: (input: BudgetInput) => post<BudgetOut>('/budgets', input),
  update: (id: number, input: Partial<Omit<BudgetInput, 'type'>>) => patch<BudgetOut>(`/budgets/${id}`, input),
  remove: (id: number) => del(`/budgets/${id}`),
  members: (id: number) => get<BudgetMemberOut[]>(`/budgets/${id}/members`),
  addMember: (id: number, email: string, role: BudgetRole) =>
    post<BudgetMemberOut>(`/budgets/${id}/members`, { email, role }),
  changeRole: (id: number, userId: number, role: BudgetRole) =>
    patch<BudgetMemberOut>(`/budgets/${id}/members/${userId}`, { role }),
  removeMember: (id: number, userId: number) => del(`/budgets/${id}/members/${userId}`),
};

export interface GoalInput {
  name: string;
  target_amount: number;
  currency: string;
  description?: string | null;
  deadline?: string | null;
}

export const goalsApi = {
  list: (query: { is_completed?: boolean } = {}) => get<GoalOut[]>('/goals', { limit: 200, ...query }),
  create: (input: GoalInput) => post<GoalOut>('/goals', input),
  update: (id: number, input: Partial<GoalInput>) => patch<GoalOut>(`/goals/${id}`, input),
  remove: (id: number) => del(`/goals/${id}`),
  deposit: (id: number, amount: number) => post<GoalOut>(`/goals/${id}/deposit`, { amount }),
  withdraw: (id: number, amount: number) => post<GoalOut>(`/goals/${id}/withdraw`, { amount }),
  close: (id: number, force = false) => post<GoalOut>(`/goals/${id}/close`, undefined, { force }),
  reopen: (id: number) => post<GoalOut>(`/goals/${id}/reopen`),
};

interface Range {
  date_from?: string;
  date_to?: string;
}

export const analyticsApi = {
  overview: (range: Range = {}) => get<OverviewOut>('/analytics/overview', { ...range }),
  monthlyTrends: (months: number) => get<MonthlyTrendsOut>('/analytics/trends/monthly', { months }),
  categories: (kind: TxKindValue, range: Range = {}) =>
    get<CategoryBreakdownOut>('/analytics/breakdown/categories', { kind, ...range }),
  periodComparison: (range: Range & { mode: 'monthly' | 'yearly' | 'custom' }) =>
    get<PeriodComparisonOut>('/analytics/comparison/period', { ...range }),
  safeToSpend: () => get<SafeToSpendOut>('/analytics/safe-to-spend'),
  budget: (budgetId: number, range: Range = {}) =>
    get<BudgetComparisonOut>(`/analytics/budgets/${budgetId}`, { ...range }),
};

export const settingsApi = {
  updateProfile: (input: { username?: string; avatar_url?: string | null; timezone?: string | null }) =>
    patch<UserOut>('/settings/profile', input),
  changeEmail: (new_email: string) => patch<UserOut>('/settings/email', { new_email }),
  updateCurrency: (default_currency: string) =>
    patch<{ default_currency: string }>('/settings/currency', { default_currency }),
  notifications: () => get<NotificationPreferences>('/settings/notifications'),
  updateNotifications: (input: Partial<NotificationPreferences>) =>
    patch<NotificationPreferences>('/settings/notifications', input),
  subscription: () => get<SubscriptionOut>('/settings/subscription'),
  upgrade: () => post<{ plan: string; message: string }>('/settings/subscription/upgrade'),
  downgrade: () => post<{ plan: string; message: string }>('/settings/subscription/downgrade'),
};

export const currenciesApi = {
  /** Rates relative to USD: amount_in_X = amount_usd * rates[X] */
  rates: () => request<Record<string, number>>('/currencies', { auth: false }),
};

export const twoFaApi = {
  setup: () => post<TwoFASetup>('/2fa/setup'),
  verify: (code: string) => post<{ message: string }>('/2fa/verify', { code }),
  disable: (code: string) => post<{ message: string }>('/2fa/disable', { code }),
};

export const securityApi = {
  events: (limit = 50, offset = 0) => get<SecurityEvents>('/security/events', { limit, offset }),
  passwordHealth: () => get<PasswordHealth>('/security/password-health'),
  checkPassword: (password: string) => post<PasswordHealth>('/security/password-health/check', { password }),
  /** Offline checks only (no leak lookup) — for the live meter; works without login */
  passwordStrength: (password: string, username?: string, email?: string) =>
    request<PasswordStrength>('/security/password-strength', { method: 'POST', body: { password, username, email }, auth: false }),
};

export const passkeysApi = {
  list: () => get<Passkey[]>('/passkeys'),
  registerOptions: () => post<PasskeyOptions>('/passkeys/register/options'),
  register: (challenge_id: string, credential: Record<string, unknown>, name?: string) =>
    post<Passkey>('/passkeys/register', { challenge_id, credential, name }),
  rename: (id: number, name: string) => patch<Passkey>(`/passkeys/${id}`, { name }),
  remove: (id: number) => del(`/passkeys/${id}`),
  loginOptions: () => request<PasskeyOptions>('/passkeys/login/options', { method: 'POST', auth: false }),
  login: (challenge_id: string, credential: Record<string, unknown>) =>
    request<TokenPair>('/passkeys/login', { method: 'POST', body: { challenge_id, credential }, auth: false }),
};
