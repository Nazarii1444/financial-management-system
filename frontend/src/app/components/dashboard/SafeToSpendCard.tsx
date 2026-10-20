import { useState } from 'react';
import { ChevronDown, Wallet } from 'lucide-react';
import { Card, CardContent } from '../ui/card';
import { Progress } from '../ui/progress';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '../ui/collapsible';
import { AsyncBlock } from '../common/States';
import { useLanguage } from '../../i18n/LanguageContext';
import { fmt } from '../../i18n/translations';
import { useApi } from '../../hooks/useApi';
import { analyticsApi } from '../../lib/api';
import type { SafeToSpendOut } from '../../types/api';

/**
 * "How much can I spend today?" — one number that already excludes upcoming
 * recurring payments and goal contributions. Refetches after every mutation
 * (notifyDataChanged), so a new expense immediately lowers it.
 */
export function SafeToSpendCard() {
  const safe = useApi(() => analyticsApi.safeToSpend(), []);

  return (
    <Card className="border-0 shadow-sm bg-gradient-to-br from-emerald-50 to-white">
      <CardContent className="pt-6">
        <AsyncBlock state={safe} className="h-[120px]">
          {(data) => <SafeToSpendBody data={data} />}
        </AsyncBlock>
      </CardContent>
    </Card>
  );
}

function SafeToSpendBody({ data }: { data: SafeToSpendOut }) {
  const { t, formatMoney, formatDate } = useLanguage();
  const [open, setOpen] = useState(false);
  const money = (n: number) => formatMoney(n, data.currency);

  const overspent = data.left_today < 0;
  const nothingAvailable = data.available_to_spend <= 0 && data.spent_today === 0;
  const usedPct = data.daily_limit > 0 ? Math.min(100, (data.spent_today / data.daily_limit) * 100) : 100;

  const rows: { label: string; value: number; sign: '' | '+' | '−' }[] = [
    { label: t.safeToSpend.balance, value: data.balance, sign: '' },
    { label: t.safeToSpend.expectedIncome, value: data.expected_income, sign: '+' },
    { label: t.safeToSpend.upcomingExpenses, value: data.upcoming_expenses, sign: '−' },
    { label: t.safeToSpend.goalReserved, value: data.goal_reserved, sign: '−' },
    { label: t.safeToSpend.goalContributions, value: data.goal_contributions, sign: '−' },
  ];

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="flex flex-col md:flex-row md:items-center gap-6">
        <div className="flex items-start gap-4 flex-1 min-w-0">
          <div className="w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center shrink-0">
            <Wallet className="w-6 h-6 text-emerald-600" />
          </div>
          <div className="min-w-0">
            <p className="text-sm text-gray-500">{t.safeToSpend.title}</p>
            <h3
              className={`text-4xl font-semibold mt-1 ${overspent || nothingAvailable ? 'text-red-600' : 'text-gray-900'}`}
              data-testid="safe-to-spend-today"
            >
              {money(Math.max(0, data.left_today))}
            </h3>
            <p className="text-xs text-gray-500 mt-1">{t.safeToSpend.hint}</p>
          </div>
        </div>

        <div className="md:w-80 space-y-2">
          {nothingAvailable ? (
            <p className="text-sm text-red-600">{t.safeToSpend.nothingLeft}</p>
          ) : (
            <>
              <div className="flex justify-between text-xs text-gray-600">
                <span>{fmt(t.safeToSpend.spentToday, { spent: money(data.spent_today), limit: money(data.daily_limit) })}</span>
              </div>
              <Progress value={usedPct} className={`h-2 ${overspent ? '[&>[data-slot=progress-indicator]]:bg-red-500 bg-red-100' : '[&>[data-slot=progress-indicator]]:bg-emerald-500 bg-emerald-100'}`} />
              {overspent && (
                <p className="text-sm text-red-600">{fmt(t.safeToSpend.overspent, { amount: money(-data.left_today) })}</p>
              )}
            </>
          )}
          <p className="text-sm text-gray-700">
            {data.days_remaining > 1 ? (
              <>
                <span className={`font-medium ${overspent ? 'text-red-600' : ''}`}>
                  {fmt(t.safeToSpend.nextDays, { amount: money(data.per_day_after_today) })}
                </span>
                <span className="text-gray-500"> · {fmt(t.safeToSpend.daysLeft, { days: data.days_remaining })}</span>
              </>
            ) : (
              <span className="text-gray-500">{t.safeToSpend.lastDay}</span>
            )}
          </p>
          <CollapsibleTrigger className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700">
            {t.safeToSpend.howCalculated}
            <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
          </CollapsibleTrigger>
        </div>
      </div>

      <CollapsibleContent>
        <div className="mt-4 pt-4 border-t border-emerald-100 grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-1 text-sm">
          <div className="space-y-1">
            {rows.map((row) => (
              <div key={row.label} className="flex justify-between gap-4">
                <span className="text-gray-600">{row.label}</span>
                <span className="text-gray-900 tabular-nums">
                  {row.sign && row.value !== 0 ? `${row.sign} ` : ''}
                  {money(row.value)}
                </span>
              </div>
            ))}
            <div className="flex justify-between gap-4 border-t border-gray-200 pt-1 font-medium">
              <span>{fmt(t.safeToSpend.available, { date: formatDate(data.month_end) })}</span>
              <span className="tabular-nums">{money(data.available_to_spend)}</span>
            </div>
            <div className="flex justify-between gap-4 text-gray-500">
              <span>{fmt(t.safeToSpend.perDayFormula, { days: data.days_remaining })}</span>
              <span className="tabular-nums">{money(data.safe_to_spend_per_day)}</span>
            </div>
          </div>
          {data.goals.some((g) => g.monthly_contribution > 0) && (
            <ul className="space-y-1 text-gray-600 mt-3 md:mt-0">
              {data.goals
                .filter((g) => g.monthly_contribution > 0)
                .map((g) => (
                  <li key={g.goal_id}>{fmt(t.safeToSpend.goalLine, { name: g.name, amount: money(g.monthly_contribution) })}</li>
                ))}
            </ul>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
