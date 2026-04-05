import { useState } from 'react';
import { Plus, Target, CheckCircle2, Trash2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Progress } from '../components/ui/progress';
import { Badge } from '../components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Input } from '../components/ui/input';
import { mockGoals } from '../data/mockData';
import { Goal } from '../types';
import { useLanguage } from '../i18n/LanguageContext';

const goalIcons = [
  { name: 'Shield', label: 'Emergency Fund' },
  { name: 'Plane', label: 'Travel' },
  { name: 'Laptop', label: 'Electronics' },
  { name: 'Gift', label: 'Gifts' },
  { name: 'Home', label: 'Home' },
  { name: 'Car', label: 'Vehicle' },
];

const goalColors = [
  '#3b82f6',
  '#10b981',
  '#8b5cf6',
  '#f59e0b',
  '#ec4899',
  '#06b6d4',
];

export function Goals() {
  const [goals, setGoals] = useState(mockGoals);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isAddFundsDialogOpen, setIsAddFundsDialogOpen] = useState(false);
  const [selectedGoal, setSelectedGoal] = useState<Goal | null>(null);

  const activeGoals = goals.filter((g) => !g.completed);
  const completedGoals = goals.filter((g) => g.completed);

  const handleCreateGoal = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);

    const newGoal: Goal = {
      id: String(goals.length + 1),
      budgetId: '1',
      name: formData.get('name') as string,
      targetAmount: Number(formData.get('targetAmount')),
      currentAmount: 0,
      currency: 'USD',
      deadline: formData.get('deadline') as string,
      color: formData.get('color') as string,
      icon: formData.get('icon') as string,
      completed: false,
    };

    setGoals([...goals, newGoal]);
    setIsCreateDialogOpen(false);
  };

  const handleAddFunds = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!selectedGoal) return;

    const formData = new FormData(e.currentTarget);
    const amount = Number(formData.get('amount'));

    setGoals(
      goals.map((g) =>
        g.id === selectedGoal.id
          ? {
              ...g,
              currentAmount: Math.min(g.currentAmount + amount, g.targetAmount),
              completed: g.currentAmount + amount >= g.targetAmount,
            }
          : g
      )
    );

    setIsAddFundsDialogOpen(false);
    setSelectedGoal(null);
  };

  const handleCompleteGoal = (goalId: string) => {
    setGoals(goals.map((g) => (g.id === goalId ? { ...g, completed: true } : g)));
  };

  const handleDeleteGoal = (goalId: string) => {
    setGoals(goals.filter((g) => g.id !== goalId));
  };

  const { t, translateGoalIcon } = useLanguage();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">{t.goals.title}</h1>
          <p className="text-sm text-gray-500 mt-1">
            {t.goals.subtitle}
          </p>
        </div>
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button size="sm">
              <Plus className="w-4 h-4 mr-2" />
              {t.goals.createGoal}
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>{t.goals.createSavingsGoal}</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreateGoal} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">{t.goals.goalName}</Label>
                <Input
                  id="name"
                  name="name"
                  placeholder={t.goals.goalNamePlaceholder}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="targetAmount">{t.goals.targetAmount}</Label>
                <Input
                  id="targetAmount"
                  name="targetAmount"
                  type="number"
                  step="0.01"
                  placeholder="0.00"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="deadline">{t.goals.deadline}</Label>
                <Input id="deadline" name="deadline" type="date" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="icon">{t.goals.icon}</Label>
                <select
                  id="icon"
                  name="icon"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                  defaultValue="Shield"
                  required
                >
                  {goalIcons.map((icon) => (
                    <option key={icon.name} value={icon.name}>
                      {translateGoalIcon(icon.label)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="color">{t.goals.color}</Label>
                <div className="flex gap-2">
                  {goalColors.map((color) => (
                    <label key={color} className="cursor-pointer">
                      <input
                        type="radio"
                        name="color"
                        value={color}
                        className="sr-only peer"
                        defaultChecked={color === goalColors[0]}
                        required
                      />
                      <div
                        className="w-10 h-10 rounded-full border-2 border-transparent peer-checked:border-gray-900 peer-checked:ring-2 peer-checked:ring-offset-2 peer-checked:ring-gray-900"
                        style={{ backgroundColor: color }}
                      />
                    </label>
                  ))}
                </div>
              </div>
              <div className="flex gap-3 pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsCreateDialogOpen(false)}
                  className="flex-1"
                >
                  {t.common.cancel}
                </Button>
                <Button type="submit" className="flex-1">
                  {t.goals.createGoalButton}
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="border-0 shadow-sm">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">{t.goals.activeGoals}</p>
                <p className="text-3xl font-semibold text-gray-900 mt-2">
                  {activeGoals.length}
                </p>
              </div>
              <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
                <Target className="w-6 h-6 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-sm">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">{t.goals.totalSaved}</p>
                <p className="text-3xl font-semibold text-gray-900 mt-2">
                  $
                  {activeGoals
                    .reduce((sum, g) => sum + g.currentAmount, 0)
                    .toLocaleString()}
                </p>
              </div>
              <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
                <svg
                  className="w-6 h-6 text-green-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"
                  />
                </svg>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-sm">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">{t.goals.completedGoals}</p>
                <p className="text-3xl font-semibold text-gray-900 mt-2">
                  {completedGoals.length}
                </p>
              </div>
              <div className="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center">
                <CheckCircle2 className="w-6 h-6 text-purple-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Active Goals */}
      <Card className="border-0 shadow-sm">
        <CardHeader>
          <CardTitle>{t.goals.activeGoals}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {activeGoals.map((goal) => {
              const progress = (goal.currentAmount / goal.targetAmount) * 100;
              const remaining = goal.targetAmount - goal.currentAmount;

              return (
                <div
                  key={goal.id}
                  className="p-6 rounded-xl border-2 border-gray-100 hover:border-gray-200 transition-colors"
                  style={{
                    background: `linear-gradient(135deg, ${goal.color}08 0%, ${goal.color}15 100%)`,
                  }}
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div
                        className="w-12 h-12 rounded-full flex items-center justify-center"
                        style={{ backgroundColor: `${goal.color}30` }}
                      >
                        <GoalIcon name={goal.icon} color={goal.color} />
                      </div>
                      <div>
                        <h3 className="font-semibold text-gray-900">{t.mockData[goal.name as keyof typeof t.mockData] || goal.name}</h3>
                        {goal.deadline && (
                          <p className="text-sm text-gray-500 mt-1">
                            {t.goals.due}: {goal.deadline}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setSelectedGoal(goal);
                          setIsAddFundsDialogOpen(true);
                        }}
                      >
                        <Plus className="w-4 h-4" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleDeleteGoal(goal.id)}
                      >
                        <Trash2 className="w-4 h-4 text-red-500" />
                      </Button>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-2xl font-semibold text-gray-900">
                        ${goal.currentAmount.toLocaleString()}
                      </span>
                      <span className="text-sm text-gray-600">
                        {t.goals.of} ${goal.targetAmount.toLocaleString()}
                      </span>
                    </div>
                    <Progress
                      value={progress}
                      className="h-3"
                      style={
                        {
                          '--progress-background': goal.color,
                        } as React.CSSProperties
                      }
                    />
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium" style={{ color: goal.color }}>
                        {progress.toFixed(1)}% {t.goals.complete}
                      </span>
                      <span className="text-sm text-gray-600">
                        ${remaining.toLocaleString()} {t.goals.remaining}
                      </span>
                    </div>
                  </div>

                  {progress >= 100 && (
                    <Button
                      className="w-full mt-4"
                      variant="outline"
                      onClick={() => handleCompleteGoal(goal.id)}
                      style={{ borderColor: goal.color, color: goal.color }}
                    >
                      <CheckCircle2 className="w-4 h-4 mr-2" />
                      {t.goals.markAsCompleted}
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Completed Goals */}
      {completedGoals.length > 0 && (
        <Card className="border-0 shadow-sm">
          <CardHeader>
            <CardTitle>{t.goals.completedGoals}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {completedGoals.map((goal) => (
                <div
                  key={goal.id}
                  className="flex items-center justify-between p-4 rounded-lg bg-green-50 border border-green-100"
                >
                  <div className="flex items-center gap-3">
                    <CheckCircle2 className="w-6 h-6 text-green-600" />
                    <div>
                      <h4 className="font-medium text-gray-900">{t.mockData[goal.name as keyof typeof t.mockData] || goal.name}</h4>
                      <p className="text-sm text-gray-600">
                        ${goal.targetAmount.toLocaleString()} {t.goals.saved}
                      </p>
                    </div>
                  </div>
                  <Badge className="bg-green-600">{t.goals.completed}</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Add Funds Dialog */}
      <Dialog open={isAddFundsDialogOpen} onOpenChange={setIsAddFundsDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {t.goals.addFundsTo} {selectedGoal ? (t.mockData[selectedGoal.name as keyof typeof t.mockData] || selectedGoal.name) : ''}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAddFunds} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="amount">{t.goals.amount}</Label>
              <Input
                id="amount"
                name="amount"
                type="number"
                step="0.01"
                placeholder="0.00"
                required
              />
              {selectedGoal && (
                <p className="text-sm text-gray-500">
                  {t.goals.current}: ${selectedGoal.currentAmount.toLocaleString()} / {t.goals.target}: $
                  {selectedGoal.targetAmount.toLocaleString()}
                </p>
              )}
            </div>
            <div className="flex gap-3 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setIsAddFundsDialogOpen(false);
                  setSelectedGoal(null);
                }}
                className="flex-1"
              >
                {t.common.cancel}
              </Button>
              <Button type="submit" className="flex-1">
                {t.goals.addFunds}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function GoalIcon({ name, color }: { name: string; color: string }) {
  const iconProps = { className: 'w-6 h-6', style: { color } };

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
    case 'Home':
      return (
        <svg {...iconProps} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
          />
        </svg>
      );
    case 'Car':
      return (
        <svg {...iconProps} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M8 7h8M5 10h14a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2zm0 0l2-4h10l2 4M7 16h.01M17 16h.01"
          />
        </svg>
      );
    default:
      return <Target {...iconProps} />;
  }
}