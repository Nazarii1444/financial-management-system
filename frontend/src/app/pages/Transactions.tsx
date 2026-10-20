import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import { toast } from 'sonner';
import {
  Plus,
  Search,
  Filter,
  ArrowUpCircle,
  ArrowDownCircle,
  ArrowLeftRight,
  Download,
  Upload,
  MoreVertical,
  Pencil,
  Trash2,
  Repeat,
  Pause,
  Play,
  CalendarDays,
  Receipt,
  Trash,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
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
import { exportsApi, recurringApi, transactionsApi, trashApi, type SearchFilters } from '../lib/api';
import { errorMessage } from '../lib/errors';
import { endOfDay, kindFromKey, kindKey, toNumber, type KindKey } from '../lib/finance';
import { AsyncBlock, EmptyState } from '../components/common/States';
import { ConfirmDialog } from '../components/common/ConfirmDialog';
import { TransactionFormDialog } from '../components/transactions/TransactionFormDialog';
import { CalendarExportDialog, type CalendarTab } from '../components/transactions/CalendarExportDialog';
import { TrashDialog } from '../components/transactions/TrashDialog';
import { ExportDialog } from '../components/transactions/ExportDialog';
import { ImportDialog } from '../components/transactions/ImportDialog';
import { CURRENCIES, type RecurringOut, type TransactionOut } from '../types/api';

const PAGE_SIZE = 50;

export function Transactions() {
  const { t, translateCategory, formatMoney, formatDate } = useLanguage();
  const { user, refreshUser } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<'all' | KindKey>('all');
  const [filterCategory, setFilterCategory] = useState('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [month, setMonth] = useState('');
  const [amountMin, setAmountMin] = useState('');
  const [amountMax, setAmountMax] = useState('');
  const [currencyFilter, setCurrencyFilter] = useState('all');
  const [receiptFilter, setReceiptFilter] = useState<'all' | 'with' | 'without'>('all');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [pages, setPages] = useState(1);
  const [trashOpen, setTrashOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);

  // Server-side search is typo-tolerant; wait for a pause in typing
  useEffect(() => {
    const id = setTimeout(() => {
      setDebouncedQuery(searchQuery.trim());
      setPages(1);
    }, 300);
    return () => clearTimeout(id);
  }, [searchQuery]);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<TransactionOut | null>(null);
  const [deletingRecurring, setDeletingRecurring] = useState<RecurringOut | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [calendarTab, setCalendarTab] = useState<CalendarTab>('file');

  // /transactions?add=1 (from the dashboard) opens the form straight away
  useEffect(() => {
    if (searchParams.get('add')) {
      setEditing(null);
      setFormOpen(true);
      setSearchParams({}, { replace: true });
    }
    // Back from Google consent: /transactions?gcal=connected|denied|error|sync_error
    const gcal = searchParams.get('gcal');
    if (gcal) {
      const messages: Record<string, [boolean, string]> = {
        connected: [true, t.calendar.connected],
        denied: [false, t.calendar.connectDenied],
        sync_error: [false, t.calendar.syncError],
      };
      const [ok, message] = messages[gcal] ?? [false, t.calendar.connectError];
      if (ok) toast.success(message);
      else toast.error(message);
      setCalendarTab('google');
      setCalendarOpen(true);
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, setSearchParams]);

  const categories = useApi(() => transactionsApi.categories(), []);
  const limit = PAGE_SIZE * pages;
  const searchFilters = useMemo<SearchFilters>(() => {
    const num = (v: string) => (v.trim() === '' || Number.isNaN(Number(v)) ? undefined : Number(v));
    return {
      q: debouncedQuery || undefined,
      kind: filterType === 'all' ? undefined : kindFromKey(filterType),
      category: filterCategory === 'all' ? undefined : filterCategory,
      date_from: dateFrom ? new Date(`${dateFrom}T00:00:00`).toISOString() : undefined,
      date_to: dateTo ? endOfDay(new Date(`${dateTo}T00:00:00`)).toISOString() : undefined,
      amount_min: num(amountMin),
      amount_max: num(amountMax),
      currency: currencyFilter === 'all' ? undefined : currencyFilter,
      has_receipt: receiptFilter === 'all' ? undefined : receiptFilter === 'with',
    };
  }, [debouncedQuery, filterType, filterCategory, dateFrom, dateTo, amountMin, amountMax, currencyFilter, receiptFilter]);

  const transactions = useApi(() => transactionsApi.search({ ...searchFilters, limit }), [searchFilters, limit]);
  const recurring = useApi(() => recurringApi.list(), []);
  const recurringCost = useApi(() => exportsApi.recurringSummary(), []);
  const filtered = transactions.data?.items ?? [];
  const totalFound = transactions.data?.total ?? 0;

  // "Month" quick filter fills the period
  const pickMonth = (value: string) => {
    setMonth(value);
    setPages(1);
    if (!value) return;
    const [y, m] = value.split('-').map(Number);
    const pad = (n: number) => String(n).padStart(2, '0');
    setDateFrom(`${value}-01`);
    setDateTo(`${value}-${pad(new Date(y, m, 0).getDate())}`);
  };

  const allCategories = useMemo(() => {
    const c = categories.data;
    if (!c) return [];
    const list = filterType === 'all' ? [...c.expense, ...c.income, ...c.transfer] : c[filterType];
    return [...new Set(list)].sort((a, b) => translateCategory(a).localeCompare(translateCategory(b)));
  }, [categories.data, filterType, translateCategory]);

  const hasFilters =
    filterType !== 'all' || filterCategory !== 'all' || dateFrom || dateTo || searchQuery ||
    amountMin || amountMax || currencyFilter !== 'all' || receiptFilter !== 'all';
  const canLoadMore = filtered.length < totalFound && limit < 1000;

  const resetFilters = () => {
    setFilterType('all');
    setFilterCategory('all');
    setDateFrom('');
    setDateTo('');
    setMonth('');
    setSearchQuery('');
    setAmountMin('');
    setAmountMax('');
    setCurrencyFilter('all');
    setReceiptFilter('all');
    setPages(1);
  };

  const handleDelete = async (tx: TransactionOut) => {
    try {
      const deleted = await transactionsApi.remove(tx.id_);
      toast.success(fmt(t.history.movedToTrash, { name: tx.name }), {
        duration: 8000,
        action: {
          label: t.history.undo,
          onClick: async () => {
            try {
              await trashApi.restore(deleted.trash_id);
              toast.success(t.history.restored);
              notifyDataChanged();
              void refreshUser();
            } catch (err) {
              toast.error(errorMessage(err, t));
            }
          },
        },
      });
      notifyDataChanged();
      void refreshUser();
    } catch (err) {
      toast.error(errorMessage(err, t));
    }
  };

  const toggleRecurring = async (rule: RecurringOut) => {
    try {
      await recurringApi.update(rule.id_, { is_active: !rule.is_active });
      toast.success(t.transactions.recurringUpdated);
      recurring.reload();
      recurringCost.reload();
    } catch (err) {
      toast.error(errorMessage(err, t));
    }
  };

  const deleteRecurring = async () => {
    if (!deletingRecurring) return;
    try {
      await recurringApi.remove(deletingRecurring.id_);
      toast.success(t.transactions.recurringDeleted);
      recurring.reload();
      recurringCost.reload();
    } catch (err) {
      toast.error(errorMessage(err, t));
    }
  };

  const currency = user?.default_currency ?? 'USD';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">{t.transactions.title}</h1>
          <p className="text-sm text-gray-500 mt-1">{t.transactions.manageIncomeExpenses}</p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setImportOpen(true)}
          >
            <Upload className="w-4 h-4 mr-2" />
            {t.transactions.import}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setExportOpen(true)}>
            <Download className="w-4 h-4 mr-2" />
            {t.history.export}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setTrashOpen(true)}>
            <Trash className="w-4 h-4 mr-2" />
            {t.history.trash}
          </Button>
          <Button
            size="sm"
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            <Plus className="w-4 h-4 mr-2" />
            {t.transactions.addTransaction}
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card className="border-0 shadow-sm">
        <CardContent className="pt-6 space-y-4">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
              <Input
                placeholder={t.history.searchPlaceholder}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
            <Select
              value={filterType}
              onValueChange={(value: 'all' | KindKey) => {
                setFilterType(value);
                setFilterCategory('all');
                setPages(1);
              }}
            >
              <SelectTrigger className="w-full md:w-[190px]">
                <Filter className="w-4 h-4 mr-2" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t.transactions.allTransactions}</SelectItem>
                <SelectItem value="income">{t.transactions.incomeOnly}</SelectItem>
                <SelectItem value="expense">{t.transactions.expensesOnly}</SelectItem>
                <SelectItem value="transfer">{t.transactions.transfersOnly}</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={filterCategory}
              onValueChange={(value) => {
                setFilterCategory(value);
                setPages(1);
              }}
            >
              <SelectTrigger className="w-full md:w-[200px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t.transactions.allCategories}</SelectItem>
                {allCategories.map((cat) => (
                  <SelectItem key={cat} value={cat}>
                    {translateCategory(cat)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-2 text-gray-600">
              {t.history.month}
              <Input type="month" className="w-[160px]" value={month} onChange={(e) => pickMonth(e.target.value)} />
            </label>
            <label className="flex items-center gap-2 text-gray-600">
              {t.transactions.from}
              <Input
                type="date"
                className="w-[160px]"
                value={dateFrom}
                onChange={(e) => {
                  setDateFrom(e.target.value);
                  setMonth('');
                  setPages(1);
                }}
              />
            </label>
            <label className="flex items-center gap-2 text-gray-600">
              {t.transactions.to}
              <Input
                type="date"
                className="w-[160px]"
                value={dateTo}
                onChange={(e) => {
                  setDateTo(e.target.value);
                  setMonth('');
                  setPages(1);
                }}
              />
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-2 text-gray-600">
              {t.history.amountFrom}
              <Input
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                className="w-[110px]"
                value={amountMin}
                onChange={(e) => {
                  setAmountMin(e.target.value);
                  setPages(1);
                }}
              />
            </label>
            <label className="flex items-center gap-2 text-gray-600">
              {t.history.amountTo}
              <Input
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                className="w-[110px]"
                value={amountMax}
                onChange={(e) => {
                  setAmountMax(e.target.value);
                  setPages(1);
                }}
              />
            </label>
            <Select
              value={currencyFilter}
              onValueChange={(value) => {
                setCurrencyFilter(value);
                setPages(1);
              }}
            >
              <SelectTrigger className="w-[150px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t.history.allCurrencies}</SelectItem>
                {CURRENCIES.map((c) => (
                  <SelectItem key={c} value={c}>
                    {c}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={receiptFilter}
              onValueChange={(value: 'all' | 'with' | 'without') => {
                setReceiptFilter(value);
                setPages(1);
              }}
            >
              <SelectTrigger className="w-[180px]">
                <Receipt className="w-4 h-4 mr-2" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t.history.receiptAny}</SelectItem>
                <SelectItem value="with">{t.history.withReceipt}</SelectItem>
                <SelectItem value="without">{t.history.withoutReceipt}</SelectItem>
              </SelectContent>
            </Select>
            {hasFilters && (
              <Button variant="ghost" size="sm" onClick={resetFilters}>
                {t.transactions.clearFilters}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Transactions List */}
      <Card className="border-0 shadow-sm">
        <CardHeader className="flex flex-row items-baseline justify-between gap-4 flex-wrap">
          <CardTitle>
            {hasFilters ? fmt(t.history.found, { count: totalFound }) : fmt(t.transactions.count, { count: totalFound })}
          </CardTitle>
          {transactions.data && totalFound > 0 && (
            <p className="text-sm text-gray-600" data-testid="search-totals">
              <span className="text-red-600 font-medium">
                {fmt(t.history.totalExpense, { amount: formatMoney(transactions.data.totals.expense, transactions.data.totals.currency) })}
              </span>
              {transactions.data.totals.income > 0 && (
                <>
                  {' · '}
                  <span className="text-green-600 font-medium">
                    {fmt(t.history.totalIncome, { amount: formatMoney(transactions.data.totals.income, transactions.data.totals.currency) })}
                  </span>
                </>
              )}
            </p>
          )}
        </CardHeader>
        <CardContent>
          <AsyncBlock state={transactions}>
            {() =>
              filtered.length === 0 ? (
                <EmptyState title={hasFilters ? t.transactions.noResults : t.dashboard.noTransactions} />
              ) : (
                <div className="space-y-3">
                  {filtered.map((tx) => {
                    const kind = kindKey(tx.kind);
                    return (
                      <div
                        key={tx.id_}
                        className="flex items-center justify-between p-4 rounded-lg border border-gray-100 hover:bg-gray-50 transition-colors"
                      >
                        <div className="flex items-center gap-4 min-w-0">
                          <div
                            className={`w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0 ${
                              kind === 'income' ? 'bg-green-100' : kind === 'expense' ? 'bg-red-100' : 'bg-blue-100'
                            }`}
                          >
                            {kind === 'income' ? (
                              <ArrowUpCircle className="w-6 h-6 text-green-600" />
                            ) : kind === 'expense' ? (
                              <ArrowDownCircle className="w-6 h-6 text-red-600" />
                            ) : (
                              <ArrowLeftRight className="w-6 h-6 text-blue-600" />
                            )}
                          </div>
                          <div className="min-w-0">
                            <h4 className="font-medium text-gray-900 truncate flex items-center gap-1.5">
                              {tx.name}
                              {tx.has_receipt && (
                                <Receipt className="w-4 h-4 text-gray-400 shrink-0" aria-label={t.history.hasReceipt}>
                                  <title>{t.history.hasReceipt}</title>
                                </Receipt>
                              )}
                            </h4>
                            <div className="flex items-center gap-2 mt-1 flex-wrap">
                              <span className="text-sm text-gray-500">{translateCategory(tx.category_name)}</span>
                              {tx.tags.length > 0 && (
                                <>
                                  <span className="text-gray-300">•</span>
                                  <div className="flex gap-1 flex-wrap">
                                    {tx.tags.map((tag) => (
                                      <Badge key={tag} variant="secondary" className="text-xs">
                                        {tag}
                                      </Badge>
                                    ))}
                                  </div>
                                </>
                              )}
                            </div>
                            {tx.note && <p className="text-xs text-gray-400 mt-1 truncate">{tx.note}</p>}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="text-right">
                            <p
                              className={`text-lg font-semibold whitespace-nowrap ${
                                kind === 'income' ? 'text-green-600' : kind === 'expense' ? 'text-red-600' : 'text-gray-700'
                              }`}
                            >
                              {kind === 'income' ? '+' : kind === 'expense' ? '−' : ''}
                              {formatMoney(toNumber(tx.amount), tx.currency || currency)}
                            </p>
                            <p className="text-sm text-gray-500 mt-1">{formatDate(tx.date)}</p>
                          </div>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                                <MoreVertical className="w-4 h-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem
                                onClick={() => {
                                  setEditing(tx);
                                  setFormOpen(true);
                                }}
                              >
                                <Pencil className="w-4 h-4 mr-2" />
                                {t.common.edit}
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem className="text-red-600" onClick={() => handleDelete(tx)}>
                                <Trash2 className="w-4 h-4 mr-2" />
                                {t.common.delete}
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </div>
                    );
                  })}
                  {canLoadMore && (
                    <div className="flex justify-center pt-2">
                      <Button variant="outline" size="sm" onClick={() => setPages((p) => p + 1)} disabled={transactions.loading}>
                        {transactions.loading ? t.common.loading : t.common.loadMore}
                      </Button>
                    </div>
                  )}
                </div>
              )
            }
          </AsyncBlock>
        </CardContent>
      </Card>

      {/* Recurring payments */}
      <Card className="border-0 shadow-sm">
        <CardHeader className="flex flex-row items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Repeat className="w-5 h-5 text-blue-600" />
              <CardTitle>{t.transactions.recurring}</CardTitle>
            </div>
            <p className="text-xs text-gray-500 mt-1.5">{t.transactions.recurringHint}</p>
            {recurringCost.data && toNumber(recurringCost.data.expense_per_year) > 0 && (
              <p className="text-sm text-gray-700 mt-2" data-testid="recurring-cost">
                {fmt(t.history.recurringCost, {
                  month: formatMoney(toNumber(recurringCost.data.expense_per_month), recurringCost.data.currency),
                  year: formatMoney(toNumber(recurringCost.data.expense_per_year), recurringCost.data.currency),
                })}
                {toNumber(recurringCost.data.subscriptions_per_year) > 0 && (
                  <span className="text-gray-500">
                    {' · '}
                    {fmt(t.history.subscriptionsCost, {
                      amount: formatMoney(toNumber(recurringCost.data.subscriptions_per_year), recurringCost.data.currency),
                    })}
                  </span>
                )}
              </p>
            )}
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setCalendarTab('file');
              setCalendarOpen(true);
            }}
          >
            <CalendarDays className="w-4 h-4 mr-1" />
            {t.calendar.button}
          </Button>
        </CardHeader>
        <CardContent>
          <AsyncBlock state={recurring}>
            {(rules) =>
              rules.length === 0 ? (
                <EmptyState title={t.transactions.noRecurring} className="py-4" />
              ) : (
                <div className="space-y-2">
                  {rules.map((rule) => {
                    const kind = kindKey(rule.kind);
                    return (
                      <div key={rule.id_} className="flex items-center justify-between p-3 rounded-lg border border-gray-100">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-gray-900 truncate">{rule.name}</span>
                            <Badge variant="outline" className="text-xs">
                              {t.frequency[rule.frequency]}
                            </Badge>
                            {!rule.is_active && (
                              <Badge variant="secondary" className="text-xs">
                                {t.transactions.paused}
                              </Badge>
                            )}
                          </div>
                          <p className="text-xs text-gray-500 mt-1">
                            {translateCategory(rule.category_name)} · {fmt(t.transactions.nextRun, { date: formatDate(rule.next_run) })}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={`font-semibold whitespace-nowrap ${kind === 'income' ? 'text-green-600' : kind === 'expense' ? 'text-red-600' : 'text-gray-700'}`}>
                            {formatMoney(toNumber(rule.amount), rule.currency || currency)}
                          </span>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            title={rule.is_active ? t.transactions.pause : t.transactions.resume}
                            onClick={() => toggleRecurring(rule)}
                          >
                            {rule.is_active ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                          </Button>
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0" title={t.common.delete} onClick={() => setDeletingRecurring(rule)}>
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </Button>
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

      <TrashDialog open={trashOpen} onOpenChange={setTrashOpen} />
      <ExportDialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        filters={searchFilters}
        matchCount={totalFound}
        month={month || new Date().toISOString().slice(0, 7)}
      />
      <CalendarExportDialog
        open={calendarOpen}
        onOpenChange={setCalendarOpen}
        activeRules={(recurring.data ?? []).filter((r) => r.is_active).length}
        initialTab={calendarTab}
      />
      <TransactionFormDialog open={formOpen} onOpenChange={setFormOpen} categories={categories.data} transaction={editing} />

      <ConfirmDialog
        open={Boolean(deletingRecurring)}
        onOpenChange={(open) => !open && setDeletingRecurring(null)}
        description={deletingRecurring ? fmt(t.transactions.deleteConfirm, { name: deletingRecurring.name }) : undefined}
        onConfirm={deleteRecurring}
      />

      {/* Import */}
      <ImportDialog open={importOpen} onOpenChange={setImportOpen} categories={categories.data} />
    </div>
  );
}
