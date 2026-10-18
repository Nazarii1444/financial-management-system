import { useEffect, useState } from 'react';
import { Plus, Minus, Target, CheckCircle2, Trash2, Pencil, MoreVertical, RotateCcw, PiggyBank } from 'lucide-react';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Progress } from '../components/ui/progress';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import { useLanguage } from '../i18n/LanguageContext';
import { fmt } from '../i18n/translations';
import { useAuth } from '../context/AuthContext';
import { notifyDataChanged, useApi } from '../hooks/useApi';
import { currenciesApi, goalsApi } from '../lib/api';
import { errorMessage } from '../lib/errors';
import { convert, daysUntil, fromDateInput, goalAppearance, toDateInput, toNumber } from '../lib/finance';
import { AsyncBlock, EmptyState } from '../components/common/States';
import { ConfirmDialog } from '../components/common/ConfirmDialog';
import { GOAL_COLORS, GOAL_ICONS, GoalIcon } from '../components/common/GoalIcon';
import { CURRENCIES, type GoalOut } from '../types/api';

type FundsMode = 'deposit' | 'withdraw';

export function Goals() {
  const { t, formatMoney, formatDate } = useLanguage();
  const { user } = useAuth();
  const goals = useApi(() => goalsApi.list(), []);
  const rates = useApi(() => currenciesApi.rates(), []);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<GoalOut | null>(null);
  const [funds, setFunds] = useState<{ goal: GoalOut; mode: FundsMode } | null>(null);
  const [deleting, setDeleting] = useState<GoalOut | null>(null);
  const [closing, setClosing] = useState<GoalOut | null>(null);

  const all = goals.data ?? [];
  const activeGoals = all.filter((g) => !g.is_completed);
  const completedGoals = all.filter((g) => g.is_completed);
  const currency = user?.default_currency ?? 'USD';
  const totalSaved = activeGoals.reduce(
    (sum, g) => sum + convert(toNumber(g.saved_amount), g.currency, currency, rates.data),
    0,
  );

  const run = async (action: () => Promise<GoalOut | void>, success: string) => {
    try {
      const result = await action();
      if (result && 'is_completed' in result && result.is_completed && success === t.goals.deposited) {
        toast.success(fmt(t.goals.reached, { name: result.name }));
      } else {
        toast.success(success);
      }
      notifyDataChanged();
    } catch (err) {
      toast.error(errorMessage(err, t));
    }
  };

  const handleComplete = (goal: GoalOut) => {
    if (toNumber(goal.saved_amount) >= toNumber(goal.target_amount)) {
      void run(() => goalsApi.close(goal.id_), t.goals.closed);
    } else {
      setClosing(goal);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">{t.goals.title}</h1>
          <p className="text-sm text-gray-500 mt-1">{t.goals.subtitle}</p>
        </div>
        <Button
          size="sm"
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
        >
          <Plus className="w-4 h-4 mr-2" />
          {t.goals.createGoal}
        </Button>
      </div>

      {/* Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="border-0 shadow-sm">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">{t.goals.activeGoals}</p>
                <p className="text-3xl font-semibold text-gray-900 mt-2">{activeGoals.length}</p>
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
                <p className="text-3xl font-semibold text-gray-900 mt-2">{formatMoney(totalSaved, currency)}</p>
              </div>
              <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
                <PiggyBank className="w-6 h-6 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-0 shadow-sm">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">{t.goals.completedGoals}</p>
                <p className="text-3xl font-semibold text-gray-900 mt-2">{completedGoals.length}</p>
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
          <AsyncBlock state={goals}>
            {() =>
              activeGoals.length === 0 ? (
                <EmptyState
                  title={t.goals.noActiveGoals}
                  action={
                    <Button size="sm" onClick={() => setFormOpen(true)}>
                      <Plus className="w-4 h-4 mr-2" />
                      {t.goals.createGoal}
                    </Button>
                  }
                />
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {activeGoals.map((goal, index) => {
                    const look = goalAppearance.get(goal.id_, index);
                    const saved = toNumber(goal.saved_amount);
                    const target = toNumber(goal.target_amount);
                    const progress = goal.progress_percent;
                    const overdue = goal.deadline ? daysUntil(goal.deadline) < 0 : false;

                    return (
                      <div
                        key={goal.id_}
                        className="p-6 rounded-xl border-2 border-gray-100 hover:border-gray-200 transition-colors"
                        style={{ background: `linear-gradient(135deg, ${look.color}08 0%, ${look.color}15 100%)` }}
                      >
                        <div className="flex items-start justify-between mb-4">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0" style={{ backgroundColor: `${look.color}30` }}>
                              <GoalIcon name={look.icon} color={look.color} />
                            </div>
                            <div className="min-w-0">
                              <h3 className="font-semibold text-gray-900 truncate">{goal.name}</h3>
                              {goal.deadline && (
                                <p className={`text-sm mt-1 ${overdue ? 'text-red-600' : 'text-gray-500'}`}>
                                  {overdue ? t.goals.overdue : t.goals.due}: {formatDate(goal.deadline)}
                                </p>
                              )}
                            </div>
                          </div>
                          <div className="flex gap-1">
                            <Button size="sm" variant="ghost" title={t.goals.addFunds} onClick={() => setFunds({ goal, mode: 'deposit' })}>
                              <Plus className="w-4 h-4" />
                            </Button>
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button size="sm" variant="ghost">
                                  <MoreVertical className="w-4 h-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end">
                                <DropdownMenuItem onClick={() => setFunds({ goal, mode: 'withdraw' })} disabled={saved <= 0}>
                                  <Minus className="w-4 h-4 mr-2" />
                                  {t.goals.withdraw}
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                  onClick={() => {
                                    setEditing(goal);
                                    setFormOpen(true);
                                  }}
                                >
                                  <Pencil className="w-4 h-4 mr-2" />
                                  {t.common.edit}
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => handleComplete(goal)}>
                                  <CheckCircle2 className="w-4 h-4 mr-2" />
                                  {t.goals.closeEarly}
                                </DropdownMenuItem>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem className="text-red-600" onClick={() => setDeleting(goal)}>
                                  <Trash2 className="w-4 h-4 mr-2" />
                                  {t.common.delete}
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          </div>
                        </div>

                        {goal.description && <p className="text-sm text-gray-600 mb-3">{goal.description}</p>}

                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <span className="text-2xl font-semibold text-gray-900">{formatMoney(saved, goal.currency)}</span>
                            <span className="text-sm text-gray-600">
                              {t.goals.of} {formatMoney(target, goal.currency)}
                            </span>
                          </div>
                          <Progress value={progress} className="h-3" style={{ '--progress-background': look.color } as React.CSSProperties} />
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium" style={{ color: look.color }}>
                              {progress.toFixed(1)}% {t.goals.complete}
                            </span>
                            <span className="text-sm text-gray-600">
                              {formatMoney(Math.max(target - saved, 0), goal.currency)} {t.goals.remaining}
                            </span>
                          </div>
                        </div>

                        {progress >= 100 && (
                          <Button
                            className="w-full mt-4"
                            variant="outline"
                            onClick={() => handleComplete(goal)}
                            style={{ borderColor: look.color, color: look.color }}
                          >
                            <CheckCircle2 className="w-4 h-4 mr-2" />
                            {t.goals.markAsCompleted}
                          </Button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )
            }
          </AsyncBlock>
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
                <div key={goal.id_} className="flex items-center justify-between p-4 rounded-lg bg-green-50 border border-green-100">
                  <div className="flex items-center gap-3">
                    <CheckCircle2 className="w-6 h-6 text-green-600" />
                    <div>
                      <h4 className="font-medium text-gray-900">{goal.name}</h4>
                      <p className="text-sm text-gray-600">
                        {formatMoney(goal.saved_amount, goal.currency)} {t.goals.saved}
                        {goal.completed_at && ` · ${formatDate(goal.completed_at)}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge className="bg-green-600">{t.goals.completed}</Badge>
                    <Button size="sm" variant="ghost" title={t.goals.reopen} onClick={() => run(() => goalsApi.reopen(goal.id_), t.goals.reopened)}>
                      <RotateCcw className="w-4 h-4" />
                    </Button>
                    <Button size="sm" variant="ghost" title={t.common.delete} onClick={() => setDeleting(goal)}>
                      <Trash2 className="w-4 h-4 text-red-500" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <GoalFormDialog open={formOpen} onOpenChange={setFormOpen} goal={editing} goalIndex={all.length} />

      {/* Add / withdraw funds */}
      <Dialog open={Boolean(funds)} onOpenChange={(open) => !open && setFunds(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {funds?.mode === 'withdraw' ? t.goals.withdrawFrom : t.goals.addFundsTo} «{funds?.goal.name}»
            </DialogTitle>
          </DialogHeader>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!funds) return;
              const amount = Number(new FormData(e.currentTarget).get('amount'));
              const { goal, mode } = funds;
              setFunds(null);
              await run(
                () => (mode === 'deposit' ? goalsApi.deposit(goal.id_, amount) : goalsApi.withdraw(goal.id_, amount)),
                mode === 'deposit' ? t.goals.deposited : t.goals.withdrawn,
              );
            }}
            className="space-y-4"
          >
            <div className="space-y-2">
              <Label htmlFor="goal-amount">
                {t.goals.amount} ({funds?.goal.currency})
              </Label>
              <Input id="goal-amount" name="amount" type="number" step="0.01" min="0.01" placeholder="0.00" autoFocus required />
              {funds && (
                <p className="text-sm text-gray-500">
                  {t.goals.current}: {formatMoney(funds.goal.saved_amount, funds.goal.currency)} / {t.goals.target}:{' '}
                  {formatMoney(funds.goal.target_amount, funds.goal.currency)}
                </p>
              )}
            </div>
            <div className="flex gap-3 pt-4">
              <Button type="button" variant="outline" onClick={() => setFunds(null)} className="flex-1">
                {t.common.cancel}
              </Button>
              <Button type="submit" className="flex-1">
                {funds?.mode === 'withdraw' ? t.goals.withdraw : t.goals.addFunds}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(open) => !open && setDeleting(null)}
        description={deleting ? fmt(t.goals.deleteConfirm, { name: deleting.name }) : undefined}
        onConfirm={async () => {
          if (!deleting) return;
          const id = deleting.id_;
          await run(() => goalsApi.remove(id), t.goals.deleted);
          goalAppearance.remove(id);
        }}
      />
      <ConfirmDialog
        open={Boolean(closing)}
        onOpenChange={(open) => !open && setClosing(null)}
        title={t.goals.closeEarly}
        description={t.goals.closeEarlyConfirm}
        confirmLabel={t.common.confirm}
        destructive={false}
        onConfirm={async () => {
          if (closing) await run(() => goalsApi.close(closing.id_, true), t.goals.closed);
        }}
      />
    </div>
  );
}

function GoalFormDialog({
  open,
  onOpenChange,
  goal,
  goalIndex,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  goal: GoalOut | null;
  goalIndex: number;
}) {
  const { t } = useLanguage();
  const { user } = useAuth();
  const [currency, setCurrency] = useState('USD');
  const [icon, setIcon] = useState<string>('Shield');
  const [color, setColor] = useState(GOAL_COLORS[0]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    const look = goal ? goalAppearance.get(goal.id_) : { icon: 'Shield', color: GOAL_COLORS[goalIndex % GOAL_COLORS.length] };
    setCurrency(goal?.currency ?? user?.default_currency ?? 'USD');
    setIcon(look.icon);
    setColor(look.color);
  }, [open, goal, goalIndex, user?.default_currency]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const deadline = String(form.get('deadline') ?? '');
    const payload = {
      name: String(form.get('name')).trim(),
      target_amount: Number(form.get('targetAmount')),
      currency,
      description: String(form.get('description') ?? '').trim() || null,
      deadline: deadline ? fromDateInput(deadline) : null,
    };
    setSaving(true);
    try {
      const saved = goal ? await goalsApi.update(goal.id_, payload) : await goalsApi.create(payload);
      goalAppearance.set(saved.id_, { icon, color });
      toast.success(goal ? t.goals.updated : t.goals.created);
      onOpenChange(false);
      notifyDataChanged();
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{goal ? t.goals.editGoal : t.goals.createSavingsGoal}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="goal-name">{t.goals.goalName}</Label>
            <Input id="goal-name" name="name" maxLength={255} defaultValue={goal?.name} placeholder={t.goals.goalNamePlaceholder} required />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2 col-span-2">
              <Label htmlFor="goal-target">{t.goals.targetAmount}</Label>
              <Input
                id="goal-target"
                name="targetAmount"
                type="number"
                step="0.01"
                min="0.01"
                defaultValue={goal ? toNumber(goal.target_amount) : undefined}
                placeholder="0.00"
                required
              />
            </div>
            <div className="space-y-2">
              <Label>{t.goals.currency}</Label>
              <Select value={currency} onValueChange={setCurrency}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CURRENCIES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="goal-deadline">
              {t.goals.deadline} <span className="text-gray-400 font-normal">({t.common.optional})</span>
            </Label>
            <Input id="goal-deadline" name="deadline" type="date" defaultValue={goal?.deadline ? toDateInput(goal.deadline) : undefined} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="goal-description">
              {t.goals.description} <span className="text-gray-400 font-normal">({t.common.optional})</span>
            </Label>
            <Textarea id="goal-description" name="description" maxLength={512} defaultValue={goal?.description ?? ''} placeholder={t.goals.descriptionPlaceholder} />
          </div>
          <div className="space-y-2">
            <Label>{t.goals.icon}</Label>
            <div className="flex gap-2 flex-wrap">
              {GOAL_ICONS.map((name) => (
                <button
                  key={name}
                  type="button"
                  title={t.goalIcons[name]}
                  onClick={() => setIcon(name)}
                  className={`w-10 h-10 rounded-lg border-2 flex items-center justify-center ${icon === name ? 'border-gray-900' : 'border-gray-200'}`}
                >
                  <GoalIcon name={name} color={color} className="w-5 h-5" />
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            <Label>{t.goals.color}</Label>
            <div className="flex gap-2">
              {GOAL_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className={`w-10 h-10 rounded-full border-2 ${color === c ? 'border-gray-900 ring-2 ring-offset-2 ring-gray-900' : 'border-transparent'}`}
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
            <p className="text-xs text-gray-400">{t.goals.appearanceLocalHint}</p>
          </div>
          <div className="flex gap-3 pt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} className="flex-1">
              {t.common.cancel}
            </Button>
            <Button type="submit" className="flex-1" disabled={saving}>
              {saving ? t.common.saving : goal ? t.common.save : t.goals.createGoalButton}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
