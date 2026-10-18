import { useMemo, useState } from 'react';
import { TrendingUp, TrendingDown, Download, Calendar, Lightbulb } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { motion } from 'motion/react';
import { useLanguage } from '../i18n/LanguageContext';
import { fmt } from '../i18n/translations';
import { useAuth } from '../context/AuthContext';
import { useApi } from '../hooks/useApi';
import { analyticsApi, currenciesApi, goalsApi, transactionsApi } from '../lib/api';
import {
  categoryColor,
  convert,
  downloadCsv,
  endOfDay,
  range,
  startOfMonth,
  startOfQuarter,
  startOfYear,
  toDateInput,
  toNumber,
} from '../lib/finance';
import { buildInsights } from '../lib/insights';
import { AsyncBlock, EmptyState } from '../components/common/States';
import { TxKind } from '../types/api';

type Period = 'month' | 'quarter' | 'year' | 'custom';

const tooltipStyle = { backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px' };

/** Monday of the week containing d (local time) */
function weekStart(d: Date) {
  const day = (d.getDay() + 6) % 7;
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() - day);
}

function Change({ value, invert = false }: { value: number | null | undefined; invert?: boolean }) {
  const { t } = useLanguage();
  if (value === null || value === undefined) return <span className="text-sm text-gray-400">{t.reports.noPrevious}</span>;
  const good = invert ? value <= 0 : value >= 0;
  const Icon = value >= 0 ? TrendingUp : TrendingDown;
  return (
    <div className="flex items-center gap-1" title={t.reports.vsPrevious}>
      <Icon className={`w-4 h-4 ${good ? 'text-green-500' : 'text-red-500'}`} />
      <span className={`text-sm ${good ? 'text-green-600' : 'text-red-600'}`}>
        {value > 0 ? '+' : ''}
        {value.toFixed(1)}%
      </span>
    </div>
  );
}

export function Reports() {
  const { t, formatMoney, formatDate, monthLabel, translateCategory } = useLanguage();
  const { user } = useAuth();
  const currency = user?.default_currency ?? 'USD';

  const [period, setPeriod] = useState<Period>('month');
  const [customFrom, setCustomFrom] = useState(toDateInput(startOfMonth()));
  const [customTo, setCustomTo] = useState(toDateInput());
  const [applied, setApplied] = useState({ from: customFrom, to: customTo });
  const [rangeOpen, setRangeOpen] = useState(false);

  const { from, to } = useMemo(() => {
    const now = new Date();
    if (period === 'custom') {
      return { from: new Date(`${applied.from}T00:00:00`), to: endOfDay(new Date(`${applied.to}T00:00:00`)) };
    }
    const start = period === 'year' ? startOfYear(now) : period === 'quarter' ? startOfQuarter(now) : startOfMonth(now);
    return { from: start, to: endOfDay(now) };
  }, [period, applied]);

  const r = range(from, to);
  const key = `${r.date_from}|${r.date_to}`;
  const trendMonths = Math.min(60, Math.max(6, (to.getFullYear() - from.getFullYear()) * 12 + to.getMonth() - from.getMonth() + 1));

  const overview = useApi(() => analyticsApi.overview(r), [key]);
  const comparison = useApi(() => analyticsApi.periodComparison({ mode: 'custom', ...r }), [key]);
  const categories = useApi(() => analyticsApi.categories(TxKind.EXPENSE, r), [key]);
  const trends = useApi(() => analyticsApi.monthlyTrends(trendMonths), [trendMonths]);
  const yoy = useApi(() => analyticsApi.monthlyTrends(24), []);
  const expenses = useApi(() => transactionsApi.list({ kind: TxKind.EXPENSE, limit: 1000, ...r }), [key]);
  const rates = useApi(() => currenciesApi.rates(), []);
  const goals = useApi(() => goalsApi.list({ is_completed: false }), []);

  const income = overview.data?.total_income ?? 0;
  const spent = overview.data?.total_expenses ?? 0;
  const savingsRate = income > 0 ? ((income - spent) / income) * 100 : null;

  // Transactions come in their own currency — convert like the backend analytics do
  const expenseRows = useMemo(
    () =>
      (expenses.data ?? []).map((tx) => ({
        ...tx,
        value: convert(toNumber(tx.amount), tx.currency || currency, currency, rates.data),
      })),
    [expenses.data, rates.data, currency],
  );
  const largest = expenseRows.reduce<(typeof expenseRows)[number] | null>((max, tx) => (!max || tx.value > max.value ? tx : max), null);

  const weekly = useMemo(() => {
    const buckets = new Map<number, number>();
    for (let w = weekStart(from); w <= to; w = new Date(w.getFullYear(), w.getMonth(), w.getDate() + 7)) {
      buckets.set(w.getTime(), 0);
    }
    for (const tx of expenseRows) {
      const k = weekStart(new Date(tx.date)).getTime();
      buckets.set(k, (buckets.get(k) ?? 0) + tx.value);
    }
    return [...buckets.entries()].map(([ts, amount]) => ({ week: formatDate(new Date(ts)), amount: Math.round(amount * 100) / 100 }));
  }, [expenseRows, from, to, formatDate]);
  const peakWeek = weekly.reduce<(typeof weekly)[number] | null>((max, w) => (!max || w.amount > max.amount ? w : max), null);

  const yoyData = useMemo(() => {
    const now = new Date();
    const cur = now.getFullYear();
    const months = yoy.data?.months ?? [];
    return Array.from({ length: 12 }, (_, i) => ({
      month: monthLabel(i + 1),
      [cur - 1]: months.find((m) => m.year === cur - 1 && m.month === i + 1)?.expenses ?? 0,
      [cur]: i <= now.getMonth() ? months.find((m) => m.year === cur && m.month === i + 1)?.expenses ?? 0 : null,
    }));
  }, [yoy.data, monthLabel]);
  const thisYear = new Date().getFullYear();

  const money = (n: number) => formatMoney(n, currency);
  const insights = buildInsights({
    t,
    translateCategory,
    money,
    categories: categories.data,
    comparison: comparison.data,
    income,
    expenses: spent,
    goals: goals.data,
    peakWeek: peakWeek && weekly.length > 1 ? { label: fmt(t.reports.week, { date: peakWeek.week }), amount: peakWeek.amount } : undefined,
  });

  const handleExport = () => {
    const rows: (string | number)[][] = [
      [t.reports.period, `${formatDate(from)} – ${formatDate(to)}`],
      [t.reports.income, income],
      [t.reports.expenses, spent],
      [t.reports.net, income - spent],
      [t.reports.savingsRate, savingsRate === null ? '' : `${savingsRate.toFixed(1)}%`],
      [],
      [t.reports.category, `${t.reports.amount} (${currency})`, t.reports.share],
      ...(categories.data?.items ?? []).map((c) => [translateCategory(c.category), c.amount, `${c.percent}%`]),
    ];
    downloadCsv(`report-${toDateInput(from)}_${toDateInput(to)}.csv`, rows);
    toast.success(t.reports.exported);
  };

  const periodLabels: Record<Exclude<Period, 'custom'>, string> = {
    month: t.reports.thisMonth,
    quarter: t.reports.thisQuarter,
    year: t.reports.thisYear,
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">{t.reports.reportsAndAnalytics}</h1>
          <p className="text-sm text-gray-500 mt-1">
            {t.reports.detailedInsights} · {formatDate(from)} – {formatDate(to)}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Popover open={rangeOpen} onOpenChange={setRangeOpen}>
            <PopoverTrigger asChild>
              <Button variant={period === 'custom' ? 'default' : 'outline'} size="sm">
                <Calendar className="w-4 h-4 mr-2" />
                {t.reports.dateRange}
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-72 space-y-3">
              <div className="space-y-1">
                <Label htmlFor="range-from">{t.transactions.from}</Label>
                <Input id="range-from" type="date" value={customFrom} max={customTo} onChange={(e) => setCustomFrom(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="range-to">{t.transactions.to}</Label>
                <Input id="range-to" type="date" value={customTo} min={customFrom} onChange={(e) => setCustomTo(e.target.value)} />
              </div>
              <Button
                className="w-full"
                size="sm"
                disabled={!customFrom || !customTo || customFrom > customTo}
                onClick={() => {
                  setApplied({ from: customFrom, to: customTo });
                  setPeriod('custom');
                  setRangeOpen(false);
                }}
              >
                {t.reports.apply}
              </Button>
            </PopoverContent>
          </Popover>
          <Button variant="outline" size="sm" onClick={handleExport}>
            <Download className="w-4 h-4 mr-2" />
            {t.reports.exportReport}
          </Button>
        </div>
      </div>

      {/* Period Selector */}
      <div className="relative">
        <div className="relative flex gap-2 p-2 bg-gradient-to-br from-white/90 via-gray-50/80 to-gray-100/90 rounded-2xl border border-white/20 shadow-lg" style={{ backdropFilter: 'blur(20px)' }}>
          {(['month', 'quarter', 'year'] as const).map((periodOption) => {
            const isActive = period === periodOption;
            return (
              <button
                key={periodOption}
                onClick={() => setPeriod(periodOption)}
                className="relative flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-medium flex-1 min-w-fit transition-all duration-200 z-10"
              >
                {isActive && (
                  <motion.div
                    layoutId="activePeriodBg"
                    className="absolute inset-0 rounded-xl bg-gradient-to-br from-blue-500 via-blue-600 to-purple-600 shadow-xl"
                    style={{ boxShadow: '0 8px 32px rgba(59, 130, 246, 0.4)' }}
                    transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  />
                )}
                <Calendar className={`w-4 h-4 relative z-10 transition-all duration-200 ${isActive ? 'text-white scale-110' : 'text-gray-600'}`} />
                <span className={`relative z-10 transition-all duration-200 ${isActive ? 'text-white font-semibold' : 'text-gray-600'}`}>
                  {periodLabels[periodOption]}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-6">
        {/* Key Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Card className="border-0 shadow-sm">
            <CardContent className="pt-6">
              <p className="text-sm text-gray-500">{t.reports.periodIncome}</p>
              <p className="text-2xl font-semibold text-gray-900 mt-2">{money(income)}</p>
              <div className="mt-2">
                <Change value={comparison.data?.change.income_pct} />
              </div>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-sm">
            <CardContent className="pt-6">
              <p className="text-sm text-gray-500">{t.reports.periodExpenses}</p>
              <p className="text-2xl font-semibold text-gray-900 mt-2">{money(spent)}</p>
              <div className="mt-2">
                <Change value={comparison.data?.change.expenses_pct} invert />
              </div>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-sm">
            <CardContent className="pt-6">
              <p className="text-sm text-gray-500">{t.reports.savingsRate}</p>
              <p className="text-2xl font-semibold text-gray-900 mt-2">{savingsRate === null ? '—' : `${savingsRate.toFixed(1)}%`}</p>
              <p className={`text-sm mt-2 ${income - spent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {t.reports.net}: {formatMoney(income - spent, currency, { signed: true })}
              </p>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-sm">
            <CardContent className="pt-6">
              <p className="text-sm text-gray-500">{t.reports.largestExpense}</p>
              <p className="text-2xl font-semibold text-gray-900 mt-2">{largest ? money(largest.value) : '—'}</p>
              <p className="text-sm text-gray-500 mt-2 truncate">
                {largest ? `${largest.name} · ${translateCategory(largest.category_name)}` : t.common.noData}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Charts Row 1 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="border-0 shadow-sm">
            <CardHeader>
              <CardTitle>{t.reports.incomeVsExpensesTrend}</CardTitle>
            </CardHeader>
            <CardContent>
              <AsyncBlock state={trends} className="h-[300px]">
                {(data) => (
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={data.months.map((m) => ({ month: `${monthLabel(m.month)} ${String(m.year).slice(2)}`, income: m.income, expenses: m.expenses }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="month" stroke="#9ca3af" fontSize={12} />
                      <YAxis stroke="#9ca3af" fontSize={12} tickFormatter={(v) => formatMoney(v, null, { compact: true })} />
                      <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => formatMoney(v, data.currency)} />
                      <Legend />
                      <Line type="monotone" dataKey="income" stroke="#10b981" strokeWidth={3} dot={{ fill: '#10b981', r: 4 }} name={t.reports.income} />
                      <Line type="monotone" dataKey="expenses" stroke="#ef4444" strokeWidth={3} dot={{ fill: '#ef4444', r: 4 }} name={t.reports.expenses} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </AsyncBlock>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-sm">
            <CardHeader>
              <CardTitle>{t.reports.spendingByCategory}</CardTitle>
            </CardHeader>
            <CardContent>
              <AsyncBlock state={categories} className="h-[300px]">
                {(data) =>
                  data.items.length === 0 ? (
                    <EmptyState title={t.common.noData} className="h-[300px]" />
                  ) : (
                    <>
                      <ResponsiveContainer width="100%" height={260}>
                        <PieChart>
                          <Pie
                            data={data.items}
                            cx="50%"
                            cy="50%"
                            labelLine={false}
                            // Items carry the backend's own `percent` field, which clashes with recharts' fraction — compute from value
                            label={({ value }) => {
                              const share = data.total > 0 ? (Number(value) / data.total) * 100 : 0;
                              return share >= 5 ? `${Math.round(share)}%` : '';
                            }}
                            outerRadius={90}
                            dataKey="amount"
                            nameKey="category"
                          >
                            {data.items.map((item) => (
                              <Cell key={item.category} fill={categoryColor(item.category)} />
                            ))}
                          </Pie>
                          <Tooltip formatter={(v: number, name: string) => [formatMoney(v, data.currency), translateCategory(name)]} />
                        </PieChart>
                      </ResponsiveContainer>
                      <div className="grid grid-cols-2 gap-2 mt-4">
                        {data.items.map((cat) => (
                          <div key={cat.category} className="flex items-center gap-2">
                            <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: categoryColor(cat.category) }} />
                            <span className="text-xs text-gray-700 truncate">
                              {translateCategory(cat.category)} · {formatMoney(cat.amount, data.currency, { compact: true })}
                            </span>
                          </div>
                        ))}
                      </div>
                    </>
                  )
                }
              </AsyncBlock>
            </CardContent>
          </Card>
        </div>

        {/* Charts Row 2 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="border-0 shadow-sm">
            <CardHeader>
              <CardTitle>{t.reports.weeklySpendingPattern}</CardTitle>
            </CardHeader>
            <CardContent>
              <AsyncBlock state={expenses} className="h-[300px]">
                {() => (
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={weekly}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="week" stroke="#9ca3af" fontSize={11} />
                      <YAxis stroke="#9ca3af" fontSize={12} tickFormatter={(v) => formatMoney(v, null, { compact: true })} />
                      <Tooltip
                        contentStyle={tooltipStyle}
                        labelFormatter={(label: string) => fmt(t.reports.week, { date: label })}
                        formatter={(v: number) => [money(v), t.reports.expenses]}
                      />
                      <Bar dataKey="amount" fill="#3b82f6" radius={[8, 8, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </AsyncBlock>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-sm">
            <CardHeader>
              <CardTitle>{t.reports.yearOverYearComparison}</CardTitle>
            </CardHeader>
            <CardContent>
              <AsyncBlock state={yoy} className="h-[300px]">
                {(data) => (
                  <ResponsiveContainer width="100%" height={300}>
                    <AreaChart data={yoyData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                      <XAxis dataKey="month" stroke="#9ca3af" fontSize={12} />
                      <YAxis stroke="#9ca3af" fontSize={12} tickFormatter={(v) => formatMoney(v, null, { compact: true })} />
                      <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => formatMoney(v, data.currency)} />
                      <Legend />
                      <Area type="monotone" dataKey={String(thisYear - 1)} stackId="1" stroke="#94a3b8" fill="#94a3b8" fillOpacity={0.6} name={String(thisYear - 1)} />
                      <Area type="monotone" dataKey={String(thisYear)} stackId="2" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.6} name={String(thisYear)} />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </AsyncBlock>
            </CardContent>
          </Card>
        </div>

        {/* Insights */}
        <Card className="border-0 shadow-sm">
          <CardHeader>
            <CardTitle>{t.reports.keyInsights}</CardTitle>
          </CardHeader>
          <CardContent>
            {insights.length === 0 ? (
              <EmptyState title={t.dashboard.noInsights} className="py-4" />
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {insights.map((insight) => {
                  const tone =
                    insight.tone === 'positive'
                      ? { box: 'bg-green-50 border-green-100', icon: 'bg-green-500' }
                      : insight.tone === 'warning'
                      ? { box: 'bg-orange-50 border-orange-100', icon: 'bg-orange-500' }
                      : { box: 'bg-blue-50 border-blue-100', icon: 'bg-blue-500' };
                  const Icon = insight.kind === 'trend' ? TrendingUp : Lightbulb;
                  return (
                    <div key={insight.id} className={`p-4 rounded-lg border ${tone.box}`}>
                      <div className="flex items-start gap-3">
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${tone.icon}`}>
                          <Icon className="w-5 h-5 text-white" />
                        </div>
                        <div>
                          <h4 className="font-medium text-gray-900 mb-1">{insight.title}</h4>
                          <p className="text-sm text-gray-600">{insight.description}</p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
