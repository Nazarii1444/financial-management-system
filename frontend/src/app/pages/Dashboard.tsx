import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Progress } from '../components/ui/progress';
import {
  TrendingUp,
  TrendingDown,
  ArrowUpRight,
  ArrowDownRight,
  DollarSign,
  Sparkles,
} from 'lucide-react';
import {
  LineChart,
  Line,
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
  TooltipProps,
} from 'recharts';
import {
  mockTransactions,
  mockGoals,
  mockAIInsights,
  monthlyData,
  categorySpending,
} from '../data/mockData';
import { motion } from 'motion/react';
import { useLanguage } from '../i18n/LanguageContext';

// Custom Tooltip for PieChart
const CustomPieTooltip = ({ active, payload, t }: TooltipProps<number, string> & { t: any }) => {
  if (active && payload && payload.length) {
    const data = payload[0];
    const categoryName = data.name as string;
    const translatedName = t.categories[categoryName as keyof typeof t.categories] || categoryName;
    
    return (
      <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-lg">
        <p className="text-sm font-medium text-gray-900">{translatedName}</p>
        <p className="text-sm text-gray-600">${data.value}</p>
      </div>
    );
  }
  return null;
};

export function Dashboard() {
  const { t } = useLanguage();

  const totalIncome = mockTransactions
    .filter((t) => t.type === 'income')
    .reduce((sum, t) => sum + t.amount, 0);

  const totalExpenses = mockTransactions
    .filter((t) => t.type === 'expense')
    .reduce((sum, t) => sum + t.amount, 0);

  const balance = totalIncome - totalExpenses;

  const recentTransactions = mockTransactions.slice(0, 5);
  const activeGoals = mockGoals.filter((g) => !g.completed);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">{t.dashboard.title}</h1>
        <p className="text-sm text-gray-500 mt-1">
          {t.dashboard.overviewActivity}
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="border-0 shadow-sm">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">{t.dashboard.totalBalance}</p>
                <h3 className="text-3xl font-semibold text-gray-900 mt-2">
                  ${balance.toLocaleString()}
                </h3>
                <div className="flex items-center gap-1 mt-2">
                  <TrendingUp className="w-4 h-4 text-green-500" />
                  <span className="text-sm text-green-600">
                    +12.5% {t.dashboard.fromLastMonth}
                  </span>
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
                <p className="text-sm text-gray-500">{t.dashboard.totalIncome}</p>
                <h3 className="text-3xl font-semibold text-gray-900 mt-2">
                  ${totalIncome.toLocaleString()}
                </h3>
                <div className="flex items-center gap-1 mt-2">
                  <TrendingUp className="w-4 h-4 text-green-500" />
                  <span className="text-sm text-gray-600">{t.dashboard.thisMonth}</span>
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
                <p className="text-sm text-gray-500">{t.dashboard.totalExpenses}</p>
                <h3 className="text-3xl font-semibold text-gray-900 mt-2">
                  ${totalExpenses.toLocaleString()}
                </h3>
                <div className="flex items-center gap-1 mt-2">
                  <TrendingDown className="w-4 h-4 text-red-500" />
                  <span className="text-sm text-gray-600">{t.dashboard.thisMonth}</span>
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
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={monthlyData.map(item => ({
                month: t.mockData[item.month as keyof typeof t.mockData],
                income: item.income,
                expenses: item.expenses
              }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="month" stroke="#9ca3af" fontSize={12} />
                <YAxis stroke="#9ca3af" fontSize={12} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#fff',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                  }}
                />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="income"
                  stackId="1"
                  stroke="#10b981"
                  fill="#10b981"
                  fillOpacity={0.6}
                  name={t.dashboard.income}
                />
                <Area
                  type="monotone"
                  dataKey="expenses"
                  stackId="2"
                  stroke="#ef4444"
                  fill="#ef4444"
                  fillOpacity={0.6}
                  name={t.dashboard.expenses}
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Spending by Category */}
        <Card className="border-0 shadow-sm">
          <CardHeader>
            <CardTitle>{t.dashboard.spendingByCategory}</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={categorySpending}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={90}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {categorySpending.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip content={<CustomPieTooltip t={t} />} />
              </PieChart>
            </ResponsiveContainer>
            <div className="space-y-2 mt-4">
              {categorySpending.slice(0, 3).map((cat) => (
                <div key={cat.name} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: cat.color }}
                    />
                    <span className="text-gray-700">{t.categories[cat.name as keyof typeof t.categories]}</span>
                  </div>
                  <span className="font-medium text-gray-900">${cat.value}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Transactions */}
        <Card className="border-0 shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>{t.dashboard.recentTransactions}</CardTitle>
            <a href="/transactions" className="text-sm text-blue-600 hover:text-blue-700">
              {t.dashboard.viewAll}
            </a>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {recentTransactions.map((transaction) => (
                <div
                  key={transaction.id}
                  className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-10 h-10 rounded-full flex items-center justify-center ${
                        transaction.type === 'income'
                          ? 'bg-green-100'
                          : 'bg-red-100'
                      }`}
                    >
                      {transaction.type === 'income' ? (
                        <ArrowUpRight className="w-5 h-5 text-green-600" />
                      ) : (
                        <ArrowDownRight className="w-5 h-5 text-red-600" />
                      )}
                    </div>
                    <div>
                      <p className="font-medium text-gray-900">{t.mockData[transaction.description as keyof typeof t.mockData]}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <p className="text-xs text-gray-500">{t.categories[transaction.category as keyof typeof t.categories]}</p>
                        {transaction.recurring && (
                          <Badge variant="outline" className="text-xs">
                            {t.dashboard.recurring}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <p
                      className={`font-semibold ${
                        transaction.type === 'income'
                          ? 'text-green-600'
                          : 'text-red-600'
                      }`}
                    >
                      {transaction.type === 'income' ? '+' : '-'}$
                      {transaction.amount.toLocaleString()}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">{transaction.date}</p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Savings Goals */}
        <Card className="border-0 shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>{t.dashboard.savingsGoals}</CardTitle>
            <a href="/goals" className="text-sm text-blue-600 hover:text-blue-700">
              {t.dashboard.viewAll}
            </a>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {activeGoals.slice(0, 3).map((goal) => {
                const progress = (goal.currentAmount / goal.targetAmount) * 100;
                return (
                  <div key={goal.id} className="p-3 rounded-lg border border-gray-100">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-8 h-8 rounded-full flex items-center justify-center"
                          style={{ backgroundColor: `${goal.color}20` }}
                        >
                          <GoalIcon name={goal.icon} color={goal.color} />
                        </div>
                        <span className="font-medium text-gray-900">{t.mockData[goal.name as keyof typeof t.mockData]}</span>
                      </div>
                      <span className="text-sm font-medium text-gray-900">
                        {progress.toFixed(0)}%
                      </span>
                    </div>
                    <Progress value={progress} className="h-2 mb-2" />
                    <div className="flex items-center justify-between text-xs text-gray-500">
                      <span>
                        ${goal.currentAmount.toLocaleString()} / $
                        {goal.targetAmount.toLocaleString()}
                      </span>
                      {goal.deadline && <span>{t.dashboard.due}: {goal.deadline}</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* AI Insights */}
      <Card className="border-0 shadow-sm bg-gradient-to-br from-purple-50 to-blue-50">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-purple-600" />
            <CardTitle>{t.dashboard.aiInsights}</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {mockAIInsights.slice(0, 4).map((insight) => (
              <div
                key={insight.id}
                className="bg-white rounded-lg p-4 border border-gray-100"
              >
                <div className="flex items-start justify-between mb-2">
                  <Badge
                    variant="outline"
                    className={
                      insight.priority === 'high'
                        ? 'border-red-200 text-red-700 bg-red-50'
                        : insight.priority === 'medium'
                        ? 'border-orange-200 text-orange-700 bg-orange-50'
                        : 'border-blue-200 text-blue-700 bg-blue-50'
                    }
                  >
                    {insight.type}
                  </Badge>
                  <span className="text-xs text-gray-400">{insight.date}</span>
                </div>
                <h4 className="font-medium text-gray-900 mb-1">{t.mockData[insight.title as keyof typeof t.mockData]}</h4>
                <p className="text-sm text-gray-600">{t.mockData[insight.description as keyof typeof t.mockData]}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function GoalIcon({ name, color }: { name: string; color: string }) {
  const iconProps = { className: 'w-4 h-4', style: { color } };

  switch (name) {
    case 'Shield':
      return (
        <svg {...iconProps} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
          />
        </svg>
      );
    case 'Plane':
      return (
        <svg {...iconProps} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M3 21v-4m0 0V5a2 2 0 012-2h6.5l1 1H21l-3 6 3 6h-8.5l-1 1H5a2 2 0 01-2-2zm9-13.5V9"
          />
        </svg>
      );
    case 'Laptop':
      return (
        <svg {...iconProps} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
          />
        </svg>
      );
    case 'Gift':
      return (
        <svg {...iconProps} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 8v13m0-13V6a2 2 0 112 2h-2zm0 0V5.5A2.5 2.5 0 109.5 8H12zm-7 4h14M5 12a2 2 0 110-4h14a2 2 0 110 4M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7"
          />
        </svg>
      );
    default:
      return <DollarSign {...iconProps} />;
  }
}