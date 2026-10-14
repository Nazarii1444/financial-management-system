import { TxKind, type TxKindValue } from '../types/api';

export const toNumber = (value: string | number | null | undefined) => {
  const n = typeof value === 'number' ? value : Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
};

export type KindKey = 'expense' | 'income' | 'transfer';

export const kindKey = (kind: TxKindValue): KindKey =>
  kind === TxKind.INCOME ? 'income' : kind === TxKind.TRANSFER ? 'transfer' : 'expense';

export const kindFromKey = (key: KindKey): TxKindValue =>
  key === 'income' ? TxKind.INCOME : key === 'transfer' ? TxKind.TRANSFER : TxKind.EXPENSE;

/** Convert between currencies using backend rates (USD pivot, same as the server) */
export const convert = (amount: number, from: string, to: string, rates: Record<string, number> | undefined) => {
  if (from === to || !rates) return amount;
  const src = rates[from];
  const dst = rates[to];
  return src && dst ? (amount / src) * dst : amount;
};

// ── Dates ────────────────────────────────────────────────────────────────────

export const startOfMonth = (d = new Date()) => new Date(d.getFullYear(), d.getMonth(), 1);
export const endOfMonth = (d = new Date()) => new Date(d.getFullYear(), d.getMonth() + 1, 0, 23, 59, 59, 999);
export const startOfQuarter = (d = new Date()) => new Date(d.getFullYear(), Math.floor(d.getMonth() / 3) * 3, 1);
export const startOfYear = (d = new Date()) => new Date(d.getFullYear(), 0, 1);
export const endOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);

/** Value for <input type="date"> in local time */
export const toDateInput = (d: Date | string = new Date()) => {
  const date = typeof d === 'string' ? new Date(d) : d;
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${mm}-${dd}`;
};

/** <input type="date"> value → ISO timestamp at local noon (keeps the same calendar day in any TZ) */
export const fromDateInput = (value: string) => new Date(`${value}T12:00:00`).toISOString();

export const daysUntil = (iso: string) => Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000);

export interface DateRange {
  date_from: string;
  date_to: string;
}

export const range = (from: Date, to: Date): DateRange => ({
  date_from: from.toISOString(),
  date_to: to.toISOString(),
});

export const monthRange = (d = new Date()) => range(startOfMonth(d), endOfMonth(d));

// ── Colors ───────────────────────────────────────────────────────────────────

const PALETTE = ['#3b82f6', '#f59e0b', '#ef4444', '#10b981', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316', '#84cc16', '#6366f1'];

export const paletteColor = (index: number) => PALETTE[index % PALETTE.length];

/** Stable color for a category name, so the same category looks the same on every chart */
export const categoryColor = (name: string) => {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[hash % PALETTE.length];
};

// ── Goal appearance (not stored by the backend yet) ──────────────────────────

export interface GoalAppearance {
  icon: string;
  color: string;
}

const GOAL_APPEARANCE_KEY = 'fms.goalAppearance';

export const goalAppearance = {
  all(): Record<number, GoalAppearance> {
    try {
      return JSON.parse(localStorage.getItem(GOAL_APPEARANCE_KEY) || '{}');
    } catch {
      return {};
    }
  },
  get(id: number, fallbackIndex = 0): GoalAppearance {
    return this.all()[id] ?? { icon: 'Shield', color: paletteColor(fallbackIndex) };
  },
  set(id: number, value: GoalAppearance) {
    try {
      localStorage.setItem(GOAL_APPEARANCE_KEY, JSON.stringify({ ...this.all(), [id]: value }));
    } catch {
      // ignore
    }
  },
  remove(id: number) {
    const all = this.all();
    delete all[id];
    try {
      localStorage.setItem(GOAL_APPEARANCE_KEY, JSON.stringify(all));
    } catch {
      // ignore
    }
  },
};

// ── CSV ──────────────────────────────────────────────────────────────────────

export function downloadCsv(filename: string, rows: (string | number)[][]) {
  const escape = (v: string | number) => {
    const s = String(v ?? '');
    return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  // BOM so Excel opens UTF-8 (Cyrillic) correctly
  const csv = '﻿' + rows.map((r) => r.map(escape).join(',')).join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const parseTags = (raw: string) =>
  raw
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
