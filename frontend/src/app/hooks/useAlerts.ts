import { useCallback, useState } from 'react';
import { analyticsApi, budgetsApi, goalsApi, recurringApi, settingsApi } from '../lib/api';
import { daysUntil, monthRange, toNumber } from '../lib/finance';
import { useApi } from './useApi';
import { useLanguage } from '../i18n/LanguageContext';
import { fmt } from '../i18n/translations';

// The backend has no notification feed yet (see docs/INTEGRATION_GAPS.md),
// so alerts are derived from live data and the user's notification preferences.

export interface Alert {
  id: string;
  type: 'warning' | 'info' | 'success';
  title: string;
  message: string;
  date: string;
  href: string;
}

const READ_KEY = 'fms.readAlerts';

function readIds(): string[] {
  try {
    return JSON.parse(localStorage.getItem(READ_KEY) || '[]');
  } catch {
    return [];
  }
}

export function useAlerts() {
  const { t, formatMoney, formatDate } = useLanguage();
  const [read, setRead] = useState<string[]>(readIds);

  const state = useApi(async () => {
    const [prefs, budgets, goals, recurring] = await Promise.all([
      settingsApi.notifications(),
      budgetsApi.list(),
      goalsApi.list(),
      recurringApi.list(),
    ]);
    const month = monthRange();
    const monthKey = month.date_from.slice(0, 7);
    const now = new Date().toISOString();

    const budgetAlerts: Alert[] = [];
    if (prefs.budget_limit_alerts) {
      const comparisons = await Promise.all(
        budgets.filter((b) => b.limit_amount).map((b) => analyticsApi.budget(b.id_, month).catch(() => null)),
      );
      for (const c of comparisons) {
        if (!c || c.utilization_percent === null || c.limit_amount === null) continue;
        if (c.utilization_percent >= 100) {
          budgetAlerts.push({
            id: `budget-over-${c.budget_id}-${monthKey}`,
            type: 'warning',
            title: t.alerts.budgetOver,
            message: fmt(t.alerts.budgetOverMsg, {
              name: c.budget_name,
              spent: formatMoney(c.actual_spent, c.currency),
              limit: formatMoney(c.limit_amount, c.currency),
            }),
            date: now,
            href: '/budgets',
          });
        } else if (c.utilization_percent >= 85) {
          budgetAlerts.push({
            id: `budget-near-${c.budget_id}-${monthKey}`,
            type: 'warning',
            title: t.alerts.budgetNear,
            message: fmt(t.alerts.budgetNearMsg, { name: c.budget_name, percent: Math.round(c.utilization_percent) }),
            date: now,
            href: '/budgets',
          });
        }
      }
    }

    const goalAlerts: Alert[] = [];
    if (prefs.goal_milestone_alerts) {
      for (const g of goals) {
        if (g.is_completed && g.completed_at && daysUntil(g.completed_at) > -7) {
          goalAlerts.push({
            id: `goal-reached-${g.id_}`,
            type: 'success',
            title: t.alerts.goalReached,
            message: fmt(t.alerts.goalReachedMsg, { name: g.name }),
            date: g.completed_at,
            href: '/goals',
          });
        } else if (!g.is_completed && g.deadline) {
          const days = daysUntil(g.deadline);
          if (days >= 0 && days <= 30) {
            goalAlerts.push({
              id: `goal-deadline-${g.id_}`,
              type: 'info',
              title: t.alerts.goalDeadline,
              message: fmt(t.alerts.goalDeadlineMsg, { name: g.name, days, percent: Math.round(g.progress_percent) }),
              date: now,
              href: '/goals',
            });
          }
        }
      }
    }

    const recurringAlerts: Alert[] = [];
    if (prefs.recurring_reminders) {
      for (const r of recurring) {
        const days = daysUntil(r.next_run);
        if (r.is_active && days >= 0 && days <= 3) {
          recurringAlerts.push({
            id: `recurring-${r.id_}-${r.next_run}`,
            type: 'info',
            title: t.alerts.recurringSoon,
            message: fmt(t.alerts.recurringSoonMsg, {
              name: r.name,
              amount: formatMoney(toNumber(r.amount), r.currency),
              date: formatDate(r.next_run),
            }),
            date: r.next_run,
            href: '/transactions',
          });
        }
      }
    }

    return [...budgetAlerts, ...goalAlerts, ...recurringAlerts];
  }, [t, formatMoney, formatDate]);

  const markAllRead = useCallback(() => {
    const ids = (state.data ?? []).map((a) => a.id);
    setRead(ids);
    try {
      localStorage.setItem(READ_KEY, JSON.stringify(ids));
    } catch {
      // ignore
    }
  }, [state.data]);

  const alerts = state.data ?? [];
  return {
    alerts,
    loading: state.loading,
    unreadCount: alerts.filter((a) => !read.includes(a.id)).length,
    isRead: (id: string) => read.includes(id),
    markAllRead,
  };
}
