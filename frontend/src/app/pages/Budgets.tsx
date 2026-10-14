import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';
import {
  Plus,
  Users,
  TrendingUp,
  AlertCircle,
  UserPlus,
  Mail,
  MoreVertical,
  Trash2,
  Shield,
  Edit2,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Progress } from '../components/ui/progress';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Input } from '../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import { Avatar, AvatarFallback } from '../components/ui/avatar';
import { toast } from 'sonner';
import { useLanguage } from '../i18n/LanguageContext';
import { fmt } from '../i18n/translations';
import { useAuth } from '../context/AuthContext';
import { useBudgets } from '../context/BudgetContext';
import { notifyDataChanged, useApi } from '../hooks/useApi';
import { analyticsApi, budgetsApi } from '../lib/api';
import { errorMessage } from '../lib/errors';
import { categoryColor, monthRange, toNumber } from '../lib/finance';
import { AsyncBlock, EmptyState, LoadingState } from '../components/common/States';
import { ConfirmDialog } from '../components/common/ConfirmDialog';
import { CURRENCIES, type BudgetOut, type BudgetMemberOut, type BudgetRole, type BudgetType } from '../types/api';

export function Budgets() {
  const { t, translateCategory, formatMoney, locale } = useLanguage();
  const { user } = useAuth();
  const { budgets, loading, error, reload, selectedBudget, selectBudget } = useBudgets();
  const [searchParams, setSearchParams] = useSearchParams();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<BudgetOut | null>(null);
  const [deleting, setDeleting] = useState<BudgetOut | null>(null);
  const [membersBudget, setMembersBudget] = useState<BudgetOut | null>(null);
  const [monthOffset, setMonthOffset] = useState(0);

  // "Create new budget" in the top bar links here with ?create=1
  useEffect(() => {
    if (searchParams.get('create')) {
      setEditing(null);
      setFormOpen(true);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const thisMonth = monthRange();
  const spending = useApi(
    async () => {
      const results = await Promise.all(budgets.map((b) => analyticsApi.budget(b.id_, thisMonth).catch(() => null)));
      return Object.fromEntries(results.filter(Boolean).map((r) => [r!.budget_id, r!]));
    },
    [budgets],
    budgets.length > 0,
  );

  const viewedMonth = new Date(new Date().getFullYear(), new Date().getMonth() + monthOffset, 1);
  const overview = useApi(
    () => analyticsApi.budget(selectedBudget!.id_, monthRange(viewedMonth)),
    [selectedBudget?.id_, monthOffset],
    Boolean(selectedBudget),
  );

  const typeLabel = (type: BudgetType) =>
    type === 'PERSONAL' ? t.budgets.personal : type === 'FAMILY' ? t.budgets.family : t.budgets.business;
  const isOwner = (b: BudgetOut) => b.owner_user_id === user?.id_;

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await budgetsApi.remove(deleting.id_);
      toast.success(t.budgets.budgetDeletedSuccess);
      reload();
      notifyDataChanged();
    } catch (err) {
      toast.error(errorMessage(err, t));
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">{t.budgets.budgetPlanning}</h1>
          <p className="text-sm text-gray-500 mt-1">{t.budgets.planTrackLimits}</p>
        </div>
        <Button
          size="sm"
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
        >
          <Plus className="w-4 h-4 mr-2" />
          {t.budgets.createBudget}
        </Button>
      </div>

      {/* Budgets */}
      {loading && budgets.length === 0 ? (
        <LoadingState />
      ) : error && budgets.length === 0 ? (
        <AsyncBlock state={{ data: undefined, loading, error, reload }}>{() => null}</AsyncBlock>
      ) : budgets.length === 0 ? (
        <Card className="border-0 shadow-sm">
          <CardContent>
            <EmptyState
              title={`${t.budgets.noBudgets}. ${t.budgets.noBudgetsHint}`}
              action={
                <Button size="sm" onClick={() => setFormOpen(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  {t.budgets.createBudget}
                </Button>
              }
            />
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {budgets.map((budget) => {
            const stats = spending.data?.[budget.id_];
            const selected = selectedBudget?.id_ === budget.id_;
            return (
              <Card
                key={budget.id_}
                className={`border-0 shadow-sm hover:shadow-md transition-shadow cursor-pointer ${selected ? 'ring-2 ring-blue-500' : ''}`}
                onClick={() => {
                  selectBudget(budget.id_);
                  setMonthOffset(0);
                }}
              >
                <CardContent className="pt-6">
                  <div className="flex items-start justify-between mb-4">
                    <div className="min-w-0">
                      <h3 className="font-semibold text-gray-900 truncate">{budget.name}</h3>
                      <div className="flex gap-2 mt-2">
                        <Badge variant="outline">{typeLabel(budget.type)}</Badge>
                        <Badge variant="secondary">{budget.currency}</Badge>
                      </div>
                    </div>
                    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                      {budget.type !== 'PERSONAL' && (
                        <Button variant="ghost" size="sm" className="h-8 px-2 text-blue-600" onClick={() => setMembersBudget(budget)} title={t.budgets.manageMembers}>
                          <Users className="w-4 h-4" />
                        </Button>
                      )}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                            <MoreVertical className="w-4 h-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() => {
                              setEditing(budget);
                              setFormOpen(true);
                            }}
                          >
                            <Edit2 className="w-4 h-4 mr-2" />
                            {t.budgets.editBudget}
                          </DropdownMenuItem>
                          {budget.type !== 'PERSONAL' && (
                            <DropdownMenuItem onClick={() => setMembersBudget(budget)}>
                              <Users className="w-4 h-4 mr-2" />
                              {t.budgets.manageMembers}
                            </DropdownMenuItem>
                          )}
                          {isOwner(budget) && (
                            <>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem className="text-red-600" onClick={() => setDeleting(budget)}>
                                <Trash2 className="w-4 h-4 mr-2" />
                                {t.budgets.deleteBudget}
                              </DropdownMenuItem>
                            </>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-500">{t.budgets.spentThisMonth}</span>
                      <span className="text-xl font-semibold text-gray-900">
                        {stats ? formatMoney(stats.actual_spent, stats.currency) : '—'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-500">{t.budgets.limit}</span>
                      <span className="text-gray-700">
                        {budget.limit_amount ? formatMoney(budget.limit_amount, budget.currency) : t.budgets.noLimit}
                      </span>
                    </div>
                    {stats?.utilization_percent != null && (
                      <Progress value={Math.min(stats.utilization_percent, 100)} className="h-2" />
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Budget Overview */}
      {selectedBudget && (
        <Card className="border-0 shadow-sm">
          <CardHeader>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <CardTitle>
                {t.budgets.monthlyBudgetOverview}: {selectedBudget.name}
              </CardTitle>
              <div className="flex items-center gap-1 text-sm">
                <Button variant="ghost" size="sm" onClick={() => setMonthOffset((m) => m - 1)} title={t.budgets.previousMonth}>
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <span className="text-gray-600 min-w-[130px] text-center capitalize">
                  {viewedMonth.toLocaleDateString(locale, { month: 'long', year: 'numeric' })}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={monthOffset >= 0}
                  onClick={() => setMonthOffset((m) => m + 1)}
                  title={t.budgets.nextMonth}
                >
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <AsyncBlock state={overview}>
              {(data) => {
                const limit = data.limit_amount;
                const progress = data.utilization_percent ?? 0;
                const isOver = limit !== null && data.actual_spent > limit;
                return (
                  <div className="space-y-6">
                    <div className="p-4 bg-gradient-to-br from-blue-50 to-purple-50 rounded-xl">
                      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                        <div>
                          <p className="text-sm text-gray-600">{t.budgets.totalSpending}</p>
                          <p className="text-2xl font-semibold text-gray-900 mt-1">
                            {formatMoney(data.actual_spent, data.currency)}
                            {limit !== null && <span className="text-gray-500"> / {formatMoney(limit, data.currency)}</span>}
                          </p>
                        </div>
                        {limit !== null && data.remaining !== null && (
                          <div className="text-right">
                            <p className="text-sm text-gray-600">{isOver ? t.budgets.overBy : t.budgets.remaining}</p>
                            <p className={`text-2xl font-semibold mt-1 ${isOver ? 'text-red-600' : 'text-green-600'}`}>
                              {formatMoney(Math.abs(data.remaining), data.currency)}
                            </p>
                          </div>
                        )}
                      </div>
                      {limit !== null ? (
                        <>
                          <Progress value={Math.min(progress, 100)} className="h-3" />
                          <div className="flex items-center justify-between mt-2">
                            <span className="text-sm text-gray-600">
                              {progress.toFixed(1)}% {t.budgets.used}
                            </span>
                            <div className="flex items-center gap-1">
                              {isOver ? (
                                <>
                                  <AlertCircle className="w-4 h-4 text-red-500" />
                                  <span className="text-sm text-red-600">{t.budgets.overLimit}</span>
                                </>
                              ) : progress > 85 ? (
                                <>
                                  <AlertCircle className="w-4 h-4 text-orange-500" />
                                  <span className="text-sm text-orange-600">{t.budgets.approachingLimit}</span>
                                </>
                              ) : (
                                <>
                                  <TrendingUp className="w-4 h-4 text-green-500" />
                                  <span className="text-sm text-green-600">{t.budgets.onTrack}</span>
                                </>
                              )}
                            </div>
                          </div>
                        </>
                      ) : (
                        <p className="text-sm text-gray-500">{t.budgets.setLimitHint}</p>
                      )}
                    </div>

                    <div className="space-y-4">
                      <div>
                        <h3 className="font-medium text-gray-900">{t.budgets.categories}</h3>
                        {selectedBudget.type !== 'PERSONAL' && <p className="text-xs text-gray-500">{t.budgets.sharedSpendingHint}</p>}
                      </div>
                      {data.by_category.length === 0 ? (
                        <EmptyState title={t.budgets.noSpending} className="py-4" />
                      ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          {data.by_category.map((item) => {
                            const share = data.actual_spent > 0 ? (item.amount / data.actual_spent) * 100 : 0;
                            const color = categoryColor(item.category);
                            return (
                              <div key={item.category} className="space-y-2">
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-3">
                                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                                    <span className="font-medium text-gray-900">{translateCategory(item.category)}</span>
                                  </div>
                                  <span className="text-sm text-gray-600">
                                    {formatMoney(item.amount, data.currency)} · {share.toFixed(0)}%
                                  </span>
                                </div>
                                <Progress
                                  value={share}
                                  className="h-2"
                                  style={{ '--progress-background': color } as React.CSSProperties}
                                />
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>

                    <div className="flex gap-3 pt-2">
                      <Button
                        variant="outline"
                        className="flex-1"
                        onClick={() => {
                          setEditing(selectedBudget);
                          setFormOpen(true);
                        }}
                      >
                        {t.budgets.adjustBudgets}
                      </Button>
                      {selectedBudget.type !== 'PERSONAL' && (
                        <Button variant="outline" className="flex-1" onClick={() => setMembersBudget(selectedBudget)}>
                          <Users className="w-4 h-4 mr-2" />
                          {t.budgets.manageMembers}
                        </Button>
                      )}
                    </div>
                  </div>
                );
              }}
            </AsyncBlock>
          </CardContent>
        </Card>
      )}

      <BudgetFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        budget={editing}
        onSaved={(b) => {
          reload();
          notifyDataChanged();
          if (!editing) selectBudget(b.id_);
        }}
      />

      <MembersDialog budget={membersBudget} onOpenChange={(open) => !open && setMembersBudget(null)} canManage={membersBudget ? isOwner(membersBudget) : false} />

      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(open) => !open && setDeleting(null)}
        description={deleting ? fmt(t.budgets.deleteConfirm, { name: deleting.name }) : undefined}
        onConfirm={handleDelete}
      />
    </div>
  );
}

// ── Create / edit ────────────────────────────────────────────────────────────

function BudgetFormDialog({
  open,
  onOpenChange,
  budget,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  budget: BudgetOut | null;
  onSaved: (budget: BudgetOut) => void;
}) {
  const { t } = useLanguage();
  const { user } = useAuth();
  const [type, setType] = useState<BudgetType>('PERSONAL');
  const [currency, setCurrency] = useState('USD');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setType(budget?.type ?? 'PERSONAL');
    setCurrency(budget?.currency ?? user?.default_currency ?? 'USD');
  }, [open, budget, user?.default_currency]);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const limitRaw = String(form.get('limit') ?? '').trim();
    const name = String(form.get('name')).trim();
    const limit_amount = limitRaw ? Number(limitRaw) : null;

    setSaving(true);
    try {
      const saved = budget
        ? await budgetsApi.update(budget.id_, { name, currency, limit_amount })
        : await budgetsApi.create({ name, type, currency, limit_amount });
      toast.success(budget ? t.budgets.budgetUpdatedSuccess : t.budgets.budgetCreatedSuccess);
      onOpenChange(false);
      onSaved(saved);
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{budget ? t.budgets.editBudget : t.budgets.createNewBudget}</DialogTitle>
          {!budget && <DialogDescription>{t.budgets.createNewBudgetDescription}</DialogDescription>}
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="budget-name">{t.budgets.budgetName}</Label>
            <Input id="budget-name" name="name" maxLength={128} defaultValue={budget?.name} placeholder={t.budgets.budgetNamePlaceholder} required />
          </div>
          <div className="space-y-2">
            <Label>{t.budgets.type}</Label>
            {/* The backend does not allow changing a budget's type after creation */}
            <Select value={type} onValueChange={(v: BudgetType) => setType(v)} disabled={Boolean(budget)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="PERSONAL">{t.budgets.personal}</SelectItem>
                <SelectItem value="FAMILY">{t.budgets.family}</SelectItem>
                <SelectItem value="BUSINESS">{t.budgets.business}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>{t.budgets.currency}</Label>
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
          <div className="space-y-2">
            <Label htmlFor="budget-limit">
              {t.budgets.limit} <span className="text-gray-400 font-normal">({t.common.optional})</span>
            </Label>
            <Input
              id="budget-limit"
              name="limit"
              type="number"
              step="0.01"
              min="0.01"
              defaultValue={budget?.limit_amount ? toNumber(budget.limit_amount) : undefined}
              placeholder={t.budgets.limitPlaceholder}
            />
          </div>
          <div className="flex gap-3 pt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} className="flex-1">
              {t.common.cancel}
            </Button>
            <Button type="submit" className="flex-1" disabled={saving}>
              {saving ? t.common.saving : budget ? t.common.save : t.budgets.create}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Members ──────────────────────────────────────────────────────────────────

function MembersDialog({
  budget,
  onOpenChange,
  canManage,
}: {
  budget: BudgetOut | null;
  onOpenChange: (open: boolean) => void;
  canManage: boolean;
}) {
  const { t } = useLanguage();
  const { user } = useAuth();
  const members = useApi(() => budgetsApi.members(budget!.id_), [budget?.id_], Boolean(budget));
  const [addOpen, setAddOpen] = useState(false);
  const [role, setRole] = useState<BudgetRole>('VIEWER');
  const [adding, setAdding] = useState(false);

  const roleLabel = (r: BudgetRole) => (r === 'OWNER' ? t.budgets.owner : r === 'EDITOR' ? t.budgets.editor : t.budgets.viewer);
  const displayName = (m: BudgetMemberOut) => m.username ?? m.email ?? `#${m.user_id}`;

  const run = async (action: () => Promise<unknown>, success: string) => {
    try {
      await action();
      toast.success(success);
      members.reload();
    } catch (err) {
      toast.error(errorMessage(err, t));
    }
  };

  const handleAdd = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!budget) return;
    const email = String(new FormData(e.currentTarget).get('email')).trim().toLowerCase();
    setAdding(true);
    await run(() => budgetsApi.addMember(budget.id_, email, role), fmt(t.budgets.memberAddedSuccess, { email }));
    setAdding(false);
    setAddOpen(false);
  };

  return (
    <>
      <Dialog open={Boolean(budget)} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Users className="w-5 h-5" />
              {t.budgets.manageMembers}
            </DialogTitle>
            <DialogDescription>
              {t.budgets.manageMembersDescription} «{budget?.name}»
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {canManage && (
              <Button
                size="sm"
                variant="outline"
                className="w-full"
                onClick={() => {
                  setRole('VIEWER');
                  setAddOpen(true);
                }}
              >
                <UserPlus className="w-4 h-4 mr-2" />
                {t.budgets.addMember}
              </Button>
            )}

            <div className="space-y-3 max-h-96 overflow-y-auto">
              <AsyncBlock state={members}>
                {(list) =>
                  list.map((member) => (
                    <div key={member.id_} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
                      <div className="flex items-center gap-3">
                        <Avatar className="w-10 h-10">
                          <AvatarFallback className="bg-blue-100 text-blue-600">{displayName(member).slice(0, 2).toUpperCase()}</AvatarFallback>
                        </Avatar>
                        <div>
                          <div className="font-medium text-gray-900">
                            {displayName(member)}
                            {member.user_id === user?.id_ && <span className="text-gray-400 font-normal"> ({t.budgets.you})</span>}
                          </div>
                          {member.email && (
                            <div className="text-sm text-gray-500 flex items-center gap-1">
                              <Mail className="w-3 h-3" />
                              {member.email}
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={member.role === 'OWNER' ? 'default' : 'outline'}>
                          {member.role === 'OWNER' && <Shield className="w-3 h-3 mr-1" />}
                          {roleLabel(member.role)}
                        </Badge>
                        {canManage && member.role !== 'OWNER' && budget && (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                                <MoreVertical className="w-4 h-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem
                                disabled={member.role === 'EDITOR'}
                                onClick={() =>
                                  run(
                                    () => budgetsApi.changeRole(budget.id_, member.user_id, 'EDITOR'),
                                    fmt(t.budgets.roleChangedSuccess, { name: displayName(member), role: t.budgets.editor }),
                                  )
                                }
                              >
                                <Edit2 className="w-4 h-4 mr-2" />
                                {t.budgets.changeToEditor}
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                disabled={member.role === 'VIEWER'}
                                onClick={() =>
                                  run(
                                    () => budgetsApi.changeRole(budget.id_, member.user_id, 'VIEWER'),
                                    fmt(t.budgets.roleChangedSuccess, { name: displayName(member), role: t.budgets.viewer }),
                                  )
                                }
                              >
                                <Edit2 className="w-4 h-4 mr-2" />
                                {t.budgets.changeToViewer}
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                className="text-red-600"
                                onClick={() =>
                                  run(
                                    () => budgetsApi.removeMember(budget.id_, member.user_id),
                                    fmt(t.budgets.memberRemovedSuccess, { name: displayName(member) }),
                                  )
                                }
                              >
                                <Trash2 className="w-4 h-4 mr-2" />
                                {t.budgets.removeMember}
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </div>
                    </div>
                  ))
                }
              </AsyncBlock>
            </div>

            <div className="flex justify-end pt-4 border-t">
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                {t.common.close}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <UserPlus className="w-5 h-5" />
              {t.budgets.addMember}
            </DialogTitle>
            <DialogDescription>{t.budgets.addMemberDescription}</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleAdd} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="member-email">{t.budgets.emailAddress}</Label>
              <Input id="member-email" name="email" type="email" placeholder={t.budgets.emailPlaceholder} required />
            </div>
            <div className="space-y-2">
              <Label>{t.budgets.role}</Label>
              <Select value={role} onValueChange={(v: BudgetRole) => setRole(v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="EDITOR">
                    {t.budgets.editor} — {t.budgets.editorDescription}
                  </SelectItem>
                  <SelectItem value="VIEWER">
                    {t.budgets.viewer} — {t.budgets.viewerDescription}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-3 pt-4">
              <Button type="button" variant="outline" onClick={() => setAddOpen(false)} className="flex-1">
                {t.common.cancel}
              </Button>
              <Button type="submit" className="flex-1" disabled={adding}>
                <Mail className="w-4 h-4 mr-2" />
                {t.budgets.sendInvite}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
