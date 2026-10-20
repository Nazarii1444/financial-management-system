import { Link } from 'react-router';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Progress } from '../components/ui/progress';
import { Button } from '../components/ui/button';
import {
  TrendingUp,
  TrendingDown,
  ArrowUpRight,
  ArrowDownRight,
  ArrowLeftRight,
  DollarSign,
  Sparkles,
} from 'lucide-react';
import {
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
import { useLanguage } from '../i18n/LanguageContext';
import { fmt } from '../i18n/translations';
import { useAuth } from '../context/AuthContext';
import { useApi } from '../hooks/useApi';
import { analyticsApi, goalsApi, transactionsApi } from '../lib/api';
import { categoryColor, goalAppearance, kindKey, monthRange, toNumber } from '../lib/finance';
import { buildInsights } from '../lib/insights';
import { AsyncBlock, EmptyState } from '../components/common/States';
import { GoalIcon } from '../components/common/GoalIcon';
import { QuickTemplates } from '../components/templates/QuickTemplates';
import { SafeToSpendCard } from '../components/dashboard/SafeToSpendCard';
import { TxKind } from '../types/api';

function ChangeBadge({ value, invert = false, suffix }: { value: number | null | undefined; invert?: boolean; suffix: string }) {
  const { t } = useLanguage();
  if (value === null || value === undefined) {
    return <span className="text-sm text-gray-500">{t.dashboard.noComparison}</span>;
  }
  const good = invert ? value <= 0 : value >= 0;
  const Icon = value >= 0 ? TrendingUp : TrendingDown;
  return (
    <div className="flex items-center gap-1">
      <Icon className={`w-4 h-4 ${good ? 'text-green-500' : 'text-red-500'}`} />
      <span className={`text-sm ${good ? 'text-green-600' : 'text-red-600'}`}>
        {value > 0 ? '+' : ''}
        {value.toFixed(1)}% {suffix}
      </span>
    </div>
  );
}

export function Dashboard() {
  const { t, formatMoney, formatDate, monthLabel, translateCategory } = useLanguage();
  const { user } = useAuth();
  const currency = user?.default_currency ?? 'USD';

  const overview = useApi(() => analyticsApi.overview(monthRange()), []);
  const comparison = useApi(() => analyticsApi.periodComparison({ mode: 'monthly' }), []);
  const trends = useApi(() => analyticsApi.monthlyTrends(6), []);
  const categories = useApi(() => analyticsApi.categories(TxKind.EXPENSE, monthRange()), []);
  const recent = useApi(() => transactionsApi.list({ limit: 5 }), []);
  const goals = useApi(() => goalsApi.list({ is_completed: false }), []);
  const txCategories = useApi(() => transactionsApi.categories(), []);

  const money = (n: number) => formatMoney(n, currency);
  const insights = buildInsights({
    t,
    translateCategory,
    money,
    categories: categories.data,
    comparison: comparison.data,
    income: overview.data?.total_income,
    expenses: overview.data?.total_expenses,
    goals: goals.data,
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">{t.dashboard.title}</h1>
        <p className="text-sm text-gray-500 mt-1">
          {user ? fmt(t.dashboard.welcome, { name: user.username }) : t.dashboard.overviewActivity}
        </p>
      </div>

      {/* Safe-to-spend: today's allowance after planned payments and goals */}
      <SafeToSpendCard />

      {/* One-click templates */}
      <QuickTemplates categories={txCategories.data} />

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="border-0 shadow-sm">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">{t.dashboard.totalBalance}</p>
                <h3 className="text-3xl font-semibold text-gray-900 mt-2">
                  {formatMoney(user?.capital ?? 0, currency)}
                </h3>
                <div className="flex items-center gap-1 mt-2">
                  {overview.data && (
                    <span className={`text-sm ${overview.data.net >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {formatMoney(overview.data.net, currency, { signed: true })} {t.dashboard.thisMonth}
                    </span>
                  )}
                </div>
              </div>
              <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
                <DollarSign className="w-6 h-6 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-sm">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">
                  {t.dashboard.totalIncome} · {t.dashboard.thisMonth}
                </p>
                <h3 className="text-3xl font-semibold text-gray-900 mt-2">
                  {formatMoney(overview.data?.total_income ?? 0, currency)}
                </h3>
                <div className="mt-2">
                  <ChangeBadge value={comparison.data?.change.income_pct} suffix={t.dashboard.fromLastMonth} />
                </div>
              </div>
              <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
                <ArrowUpRight className="w-6 h-6 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-sm">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">
                  {t.dashboard.totalExpenses} · {t.dashboard.thisMonth}
                </p>
                <h3 className="text-3xl font-semibold text-gray-900 mt-2">
                  {formatMoney(overview.data?.total_expenses ?? 0, currency)}
                </h3>
                <div className="mt-2">
                  <ChangeBadge value={comparison.data?.change.expenses_pct} invert suffix={t.dashboard.fromLastMonth} />
                </div>
              </div>
              <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center">
                <ArrowDownRight className="w-6 h-6 text-red-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Income vs Expenses Chart */}
        <Card className="lg:col-span-2 border-0 shadow-sm">
          <CardHeader>
            <CardTitle>{t.dashboard.incomeVsExpenses}</CardTitle>
          </CardHeader>
          <CardContent>
            <AsyncBlock state={trends} className="h-[300px]">
              {(data) => (
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart
                    data={data.months.map((m) => ({
                      month: monthLabel(m.month),
                      income: m.income,
                      expenses: m.expenses,
                    }))}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="month" stroke="#9ca3af" fontSize={12} />
                    <YAxis stroke="#9ca3af" fontSize={12} tickFormatter={(v) => formatMoney(v, null, { compact: true })} />
                    <Tooltip
                      formatter={(value: number) => formatMoney(value, data.currency)}
                      contentStyle={{ backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px' }}
                    />
                    <Legend />
                    <Area type="monotone" dataKey="income" stackId="1" stroke="#10b981" fill="#10b981" fillOpacity={0.6} name={t.dashboard.income} />
                    <Area type="monotone" dataKey="expenses" stackId="2" stroke="#ef4444" fill="#ef4444" fillOpacity={0.6} name={t.dashboard.expenses} />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </AsyncBlock>
          </CardContent>
        </Card>

        {/* Spending by Category */}
        <Card className="border-0 shadow-sm">
          <CardHeader>
            <CardTitle>{t.dashboard.spendingByCategory}</CardTitle>
            <p className="text-xs text-gray-500">{t.dashboard.thisMonthHint}</p>
          </CardHeader>
          <CardContent>
            <AsyncBlock state={categories} className="h-[300px]">
              {(data) =>
                data.items.length === 0 ? (
                  <EmptyState title={t.common.noData} className="h-[300px]" />
                ) : (
                  <>
                    <ResponsiveContainer width="100%" height={220}>
                      <PieChart>
                        <Pie data={data.items} cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={2} dataKey="amount" nameKey="category">
                          {data.items.map((item) => (
                            <Cell key={item.category} fill={categoryColor(item.category)} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(value: number, name: string) => [formatMoney(value, data.currency), translateCategory(name)]} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="space-y-2 mt-4">
                      {data.items.slice(0, 4).map((cat) => (
                        <div key={cat.category} className="flex items-center justify-between text-sm">
                          <div className="flex items-center gap-2">
                            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: categoryColor(cat.category) }} />
                            <span className="text-gray-700">{translateCategory(cat.category)}</span>
                          </div>
                          <span className="font-medium text-gray-900">{formatMoney(cat.amount, data.currency)}</span>
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Transactions */}
        <Card className="border-0 shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>{t.dashboard.recentTransactions}</CardTitle>
            <Link to="/transactions" className="text-sm text-blue-600 hover:text-blue-700">
              {t.dashboard.viewAll}
            </Link>
          </CardHeader>
          <CardContent>
            <AsyncBlock state={recent}>
              {(items) =>
                items.length === 0 ? (
                  <EmptyState
                    title={t.dashboard.noTransactions}
                    action={
                      <Button asChild size="sm">
                        <Link to="/transactions?add=1">{t.dashboard.addFirstTransaction}</Link>
                      </Button>
                    }
                  />
                ) : (
                  <div className="space-y-4">
                    {items.map((tx) => {
                      const kind = kindKey(tx.kind);
                      return (
                        <div key={tx.id_} className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 transition-colors">
                          <div className="flex items-center gap-3">
                            <div
                              className={`w-10 h-10 rounded-full flex items-center justify-center ${
                                kind === 'income' ? 'bg-green-100' : kind === 'expense' ? 'bg-red-100' : 'bg-blue-100'
                              }`}
                            >
                              {kind === 'income' ? (
                                <ArrowUpRight className="w-5 h-5 text-green-600" />
                              ) : kind === 'expense' ? (
                                <ArrowDownRight className="w-5 h-5 text-red-600" />
                              ) : (
                                <ArrowLeftRight className="w-5 h-5 text-blue-600" />
                              )}
                            </div>
                            <div>
                              <p className="font-medium text-gray-900">{tx.name}</p>
                              <p className="text-xs text-gray-500 mt-1">{translateCategory(tx.category_name)}</p>
                            </div>
                          </div>
                          <div className="text-right">
                            <p
                              className={`font-semibold ${
                                kind === 'income' ? 'text-green-600' : kind === 'expense' ? 'text-red-600' : 'text-gray-700'
                              }`}
                            >
                              {kind === 'income' ? '+' : kind === 'expense' ? '−' : ''}
                              {formatMoney(toNumber(tx.amount), tx.currency || currency)}
                            </p>
                            <p className="text-xs text-gray-500 mt-1">{formatDate(tx.date)}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )
              }
            </AsyncBlock>
          </CardContent>
        </Card>

        {/* Savings Goals */}
        <Card className="border-0 shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>{t.dashboard.savingsGoals}</CardTitle>
            <Link to="/goals" className="text-sm text-blue-600 hover:text-blue-700">
              {t.dashboard.viewAll}
            </Link>
          </CardHeader>
          <CardContent>
            <AsyncBlock state={goals}>
              {(items) =>
                items.length === 0 ? (
                  <EmptyState
                    title={t.dashboard.noGoals}
                    action={
                      <Button asChild size="sm" variant="outline">
                        <Link to="/goals">{t.dashboard.createFirstGoal}</Link>
                      </Button>
                    }
                  />
                ) : (
                  <div className="space-y-4">
                    {items.slice(0, 3).map((goal, index) => {
                      const look = goalAppearance.get(goal.id_, index);
                      return (
                        <div key={goal.id_} className="p-3 rounded-lg border border-gray-100">
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <div className="w-8 h-8 rounded-full flex items-center justify-center" style={{ backgroundColor: `${look.color}20` }}>
                                <GoalIcon name={look.icon} color={look.color} className="w-4 h-4" />
                              </div>
                              <span className="font-medium text-gray-900">{goal.name}</span>
                            </div>
                            <span className="text-sm font-medium text-gray-900">{Math.round(goal.progress_percent)}%</span>
                          </div>
                          <Progress value={goal.progress_percent} className="h-2 mb-2" />
                          <div className="flex items-center justify-between text-xs text-gray-500">
                            <span>
                              {formatMoney(goal.saved_amount, goal.currency)} / {formatMoney(goal.target_amount, goal.currency)}
                            </span>
                            {goal.deadline && (
                              <span>
                                {t.dashboard.due}: {formatDate(goal.deadline)}
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )
              }
            </AsyncBlock>
          </CardContent>
        </Card>
      </div>

      {/* Insights */}
      <Card className="border-0 shadow-sm bg-gradient-to-br from-purple-50 to-blue-50">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-purple-600" />
            <CardTitle>{t.dashboard.insights}</CardTitle>
          </div>
          <p className="text-xs text-gray-500">{t.dashboard.insightsHint}</p>
        </CardHeader>
        <CardContent>
          {insights.length === 0 ? (
            <EmptyState title={t.dashboard.noInsights} className="py-4" />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {insights.slice(0, 4).map((insight) => (
                <div key={insight.id} className="bg-white rounded-lg p-4 border border-gray-100">
                  <div className="flex items-start justify-between mb-2">
                    <Badge
                      variant="outline"
                      className={
                        insight.tone === 'warning'
                          ? 'border-orange-200 text-orange-700 bg-orange-50'
                          : insight.tone === 'positive'
                          ? 'border-green-200 text-green-700 bg-green-50'
                          : 'border-blue-200 text-blue-700 bg-blue-50'
                      }
                    >
                      {t.insights[insight.kind]}
                    </Badge>
                  </div>
                  <h4 className="font-medium text-gray-900 mb-1">{insight.title}</h4>
                  <p className="text-sm text-gray-600">{insight.description}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
