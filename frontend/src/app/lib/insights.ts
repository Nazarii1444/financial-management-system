import type { CategoryBreakdownOut, GoalOut, PeriodComparisonOut } from '../types/api';
import type { Translations } from '../i18n/translations';
import { fmt } from '../i18n/translations';

// Rule-based insights computed from real analytics data.
// The backend has no AI/insights endpoint yet (see docs/INTEGRATION_GAPS.md).

export interface Insight {
  id: string;
  kind: 'spending' | 'trend' | 'savings' | 'goal';
  tone: 'positive' | 'warning' | 'info';
  title: string;
  description: string;
}

interface InsightInput {
  t: Translations;
  translateCategory: (name: string) => string;
  money: (amount: number) => string;
  categories?: CategoryBreakdownOut;
  comparison?: PeriodComparisonOut;
  income?: number;
  expenses?: number;
  goals?: GoalOut[];
  peakWeek?: { label: string; amount: number };
}

const pct = (n: number) => Math.round(Math.abs(n));

export function buildInsights(input: InsightInput): Insight[] {
  const { t, translateCategory, money, categories, comparison, income = 0, expenses = 0, goals, peakWeek } = input;
  const out: Insight[] = [];

  const top = categories?.items[0];
  if (top && categories && categories.total > 0) {
    out.push({
      id: 'top-category',
      kind: 'spending',
      tone: top.percent >= 40 ? 'warning' : 'info',
      title: t.insights.topCategoryTitle,
      description: fmt(t.insights.topCategoryDesc, {
        category: translateCategory(top.category),
        percent: pct(top.percent),
        amount: money(top.amount),
      }),
    });
  }

  const expPct = comparison?.change.expenses_pct;
  if (expPct !== null && expPct !== undefined && Math.abs(expPct) >= 5) {
    out.push({
      id: 'expenses-trend',
      kind: 'trend',
      tone: expPct > 0 ? 'warning' : 'positive',
      title: expPct > 0 ? t.insights.expensesUpTitle : t.insights.expensesDownTitle,
      description: fmt(expPct > 0 ? t.insights.expensesUpDesc : t.insights.expensesDownDesc, { percent: pct(expPct) }),
    });
  }

  const incPct = comparison?.change.income_pct;
  if (incPct !== null && incPct !== undefined && incPct >= 5) {
    out.push({
      id: 'income-trend',
      kind: 'trend',
      tone: 'positive',
      title: t.insights.incomeUpTitle,
      description: fmt(t.insights.incomeUpDesc, { percent: pct(incPct) }),
    });
  }

  if (income > 0) {
    const rate = ((income - expenses) / income) * 100;
    if (rate < 0) {
      out.push({
        id: 'overspend',
        kind: 'savings',
        tone: 'warning',
        title: t.insights.overspendTitle,
        description: fmt(t.insights.overspendDesc, { amount: money(expenses - income) }),
      });
    } else {
      out.push({
        id: 'savings-rate',
        kind: 'savings',
        tone: rate >= 20 ? 'positive' : 'warning',
        title: rate >= 20 ? t.insights.savingsGoodTitle : t.insights.savingsLowTitle,
        description: fmt(rate >= 20 ? t.insights.savingsGoodDesc : t.insights.savingsLowDesc, { percent: pct(rate) }),
      });
    }
  } else if (expenses > 0) {
    out.push({
      id: 'overspend',
      kind: 'savings',
      tone: 'warning',
      title: t.insights.overspendTitle,
      description: fmt(t.insights.overspendDesc, { amount: money(expenses) }),
    });
  }

  if (peakWeek && peakWeek.amount > 0) {
    out.push({
      id: 'peak-week',
      kind: 'spending',
      tone: 'info',
      title: t.insights.peakWeekTitle,
      description: fmt(t.insights.peakWeekDesc, { week: peakWeek.label, amount: money(peakWeek.amount) }),
    });
  }

  const closest = (goals ?? [])
    .filter((g) => !g.is_completed && g.progress_percent >= 50)
    .sort((a, b) => b.progress_percent - a.progress_percent)[0];
  if (closest) {
    out.push({
      id: `goal-${closest.id_}`,
      kind: 'goal',
      tone: 'positive',
      title: t.insights.goalCloseTitle,
      description: fmt(t.insights.goalCloseDesc, { name: closest.name, percent: Math.round(closest.progress_percent) }),
    });
  }

  return out;
}
