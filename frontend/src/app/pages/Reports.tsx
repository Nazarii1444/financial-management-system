import { useState } from 'react';
import { TrendingUp, TrendingDown, Download, Calendar } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
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
  TooltipProps,
} from 'recharts';
import { monthlyData, categorySpending } from '../data/mockData';
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

const yearComparison = [
  { month: 'jan', '2025': 4800, '2026': 5000 },
  { month: 'feb', '2025': 4600, '2026': 5300 },
  { month: 'mar', '2025': 5200, '2026': 5800 },
  { month: 'apr', '2025': 4900, '2026': 0 },
  { month: 'may', '2025': 5100, '2026': 0 },
  { month: 'jun', '2025': 5400, '2026': 0 },
];

const weeklySpending = [
  { week: 'week1', spending: 450 },
  { week: 'week2', spending: 620 },
  { week: 'week3', spending: 580 },
  { week: 'week4', spending: 750 },
];

export function Reports() {
  const [period, setPeriod] = useState<'month' | 'quarter' | 'year'>('month');
  const { t } = useLanguage();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">{t.reports.reportsAndAnalytics}</h1>
          <p className="text-sm text-gray-500 mt-1">
            {t.reports.detailedInsights}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm">
            <Calendar className="w-4 h-4 mr-2" />
            {t.reports.dateRange}
          </Button>
          <Button variant="outline" size="sm">
            <Download className="w-4 h-4 mr-2" />
            {t.reports.exportReport}
          </Button>
        </div>
      </div>

      {/* Liquid Glass Period Selector */}
      <div className="relative">
        <div className="relative flex gap-2 p-2 bg-gradient-to-br from-white/90 via-gray-50/80 to-gray-100/90 rounded-2xl border border-white/20 shadow-lg" style={{ backdropFilter: 'blur(20px)' }}>
          {(['month', 'quarter', 'year'] as const).map((periodOption) => {
            const isActive = period === periodOption;
            const labels = {
              month: t.reports.thisMonth,
              quarter: t.reports.thisQuarter,
              year: t.reports.thisYear
            };
            
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
                    style={{
                      boxShadow: '0 8px 32px rgba(59, 130, 246, 0.4)',
                    }}
                    transition={{
                      type: 'spring',
                      stiffness: 400,
                      damping: 30,
                    }}
                  />
                )}
                
                <Calendar className={`w-4 h-4 relative z-10 transition-all duration-200 ${isActive ? 'text-white scale-110' : 'text-gray-600'}`} />
                <span className={`relative z-10 transition-all duration-200 ${isActive ? 'text-white font-semibold' : 'text-gray-600'}`}>
                  {labels[periodOption]}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-6">{/* Key Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <Card className="border-0 shadow-sm">
            <CardContent className="pt-6">
              <p className="text-sm text-gray-500">{t.reports.averageMonthlyIncome}</p>
              <p className="text-2xl font-semibold text-gray-900 mt-2">$5,367</p>
              <div className="flex items-center gap-1 mt-2">
                <TrendingUp className="w-4 h-4 text-green-500" />
                <span className="text-sm text-green-600">+8.2%</span>
              </div>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-sm">
            <CardContent className="pt-6">
              <p className="text-sm text-gray-500">{t.reports.averageMonthlyExpenses}</p>
              <p className="text-2xl font-semibold text-gray-900 mt-2">$4,121</p>
              <div className="flex items-center gap-1 mt-2">
                <TrendingDown className="w-4 h-4 text-green-500" />
                <span className="text-sm text-green-600">-3.1%</span>
              </div>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-sm">
            <CardContent className="pt-6">
              <p className="text-sm text-gray-500">{t.reports.savingsRate}</p>
              <p className="text-2xl font-semibold text-gray-900 mt-2">23.2%</p>
              <div className="flex items-center gap-1 mt-2">
                <TrendingUp className="w-4 h-4 text-green-500" />
                <span className="text-sm text-green-600">+5.4%</span>
              </div>
            </CardContent>
          </Card>

          <Card className="border-0 shadow-sm">
            <CardContent className="pt-6">
              <p className="text-sm text-gray-500">{t.reports.largestExpense}</p>
              <p className="text-2xl font-semibold text-gray-900 mt-2">$1,200</p>
              <p className="text-sm text-gray-500 mt-2">{t.reports.billsAndUtilities}</p>
            </CardContent>
          </Card>
        </div>

        {/* Charts Row 1 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Income vs Expenses Trend */}
          <Card className="border-0 shadow-sm">
            <CardHeader>
              <CardTitle>{t.reports.incomeVsExpensesTrend}</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={monthlyData.map(item => ({
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
                  <Line
                    type="monotone"
                    dataKey="income"
                    stroke="#10b981"
                    strokeWidth={3}
                    dot={{ fill: '#10b981', r: 4 }}
                    name={t.reports.income}
                  />
                  <Line
                    type="monotone"
                    dataKey="expenses"
                    stroke="#ef4444"
                    strokeWidth={3}
                    dot={{ fill: '#ef4444', r: 4 }}
                    name={t.reports.expenses}
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Category Breakdown */}
          <Card className="border-0 shadow-sm">
            <CardHeader>
              <CardTitle>{t.reports.spendingByCategory}</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={categorySpending}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent }) => {
                      const translatedName = t.categories[name as keyof typeof t.categories] || name;
                      return `${(percent * 100).toFixed(0)}%`;
                    }}
                    outerRadius={80}
                    dataKey="value"
                  >
                    {categorySpending.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomPieTooltip t={t} />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="grid grid-cols-2 gap-2 mt-4">
                {categorySpending.map((cat) => (
                  <div key={cat.name} className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-full flex-shrink-0"
                      style={{ backgroundColor: cat.color }}
                    />
                    <span className="text-xs text-gray-700 truncate">
                      {t.categories[cat.name as keyof typeof t.categories]}
                    </span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Charts Row 2 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Weekly Spending */}
          <Card className="border-0 shadow-sm">
            <CardHeader>
              <CardTitle>{t.reports.weeklySpendingPattern}</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={weeklySpending.map(item => ({
                  week: t.mockData[item.week as keyof typeof t.mockData],
                  spending: item.spending
                }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="week" stroke="#9ca3af" fontSize={12} />
                  <YAxis stroke="#9ca3af" fontSize={12} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#fff',
                      border: '1px solid #e5e7eb',
                      borderRadius: '8px',
                    }}
                    formatter={(value: number) => `$${value}`}
                  />
                  <Bar dataKey="spending" fill="#3b82f6" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Year over Year */}
          <Card className="border-0 shadow-sm">
            <CardHeader>
              <CardTitle>{t.reports.yearOverYearComparison}</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={yearComparison.map(item => ({
                  month: t.mockData[item.month as keyof typeof t.mockData],
                  '2025': item['2025'],
                  '2026': item['2026']
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
                    dataKey="2025"
                    stackId="1"
                    stroke="#94a3b8"
                    fill="#94a3b8"
                    fillOpacity={0.6}
                    name="2025"
                  />
                  <Area
                    type="monotone"
                    dataKey="2026"
                    stackId="2"
                    stroke="#3b82f6"
                    fill="#3b82f6"
                    fillOpacity={0.6}
                    name="2026"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>

        {/* Insights Summary */}
        <Card className="border-0 shadow-sm">
          <CardHeader>
            <CardTitle>{t.reports.keyInsights}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-lg bg-green-50 border border-green-100">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 bg-green-500 rounded-full flex items-center justify-center flex-shrink-0">
                    <TrendingUp className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <h4 className="font-medium text-gray-900 mb-1">
                      {t.reports.positiveTrend}
                    </h4>
                    <p className="text-sm text-gray-600">
                      {t.reports.positiveTrendDesc}
                    </p>
                  </div>
                </div>
              </div>

              <div className="p-4 rounded-lg bg-blue-50 border border-blue-100">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 bg-blue-500 rounded-full flex items-center justify-center flex-shrink-0">
                    <svg
                      className="w-5 h-5 text-white"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
                      />
                    </svg>
                  </div>
                  <div>
                    <h4 className="font-medium text-gray-900 mb-1">
                      {t.reports.greatSavingsRate}
                    </h4>
                    <p className="text-sm text-gray-600">
                      {t.reports.greatSavingsRateDesc}
                    </p>
                  </div>
                </div>
              </div>

              <div className="p-4 rounded-lg bg-orange-50 border border-orange-100">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 bg-orange-500 rounded-full flex items-center justify-center flex-shrink-0">
                    <svg
                      className="w-5 h-5 text-white"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                      />
                    </svg>
                  </div>
                  <div>
                    <h4 className="font-medium text-gray-900 mb-1">
                      {t.reports.highWeekSpending}
                    </h4>
                    <p className="text-sm text-gray-600">
                      {t.reports.highWeekSpendingDesc}
                    </p>
                  </div>
                </div>
              </div>

              <div className="p-4 rounded-lg bg-purple-50 border border-purple-100">
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 bg-purple-500 rounded-full flex items-center justify-center flex-shrink-0">
                    <svg
                      className="w-5 h-5 text-white"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                      />
                    </svg>
                  </div>
                  <div>
                    <h4 className="font-medium text-gray-900 mb-1">
                      {t.reports.topCategory}
                    </h4>
                    <p className="text-sm text-gray-600">
                      {t.reports.topCategoryDesc}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}