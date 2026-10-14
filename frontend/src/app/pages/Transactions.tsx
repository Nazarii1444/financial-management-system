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
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../components/ui/dialog';
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
import { recurringApi, transactionsApi } from '../lib/api';
import { errorMessage } from '../lib/errors';
import { downloadCsv, endOfDay, kindFromKey, kindKey, toDateInput, toNumber, type KindKey } from '../lib/finance';
import { AsyncBlock, EmptyState } from '../components/common/States';
import { ConfirmDialog } from '../components/common/ConfirmDialog';
import { TransactionFormDialog } from '../components/transactions/TransactionFormDialog';
import type { RecurringOut, TransactionOut } from '../types/api';

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
  const [pages, setPages] = useState(1);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<TransactionOut | null>(null);
  const [deleting, setDeleting] = useState<TransactionOut | null>(null);
  const [deletingRecurring, setDeletingRecurring] = useState<RecurringOut | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);

  // /transactions?add=1 (from the dashboard) opens the form straight away
  useEffect(() => {
    if (searchParams.get('add')) {
      setEditing(null);
      setFormOpen(true);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const categories = useApi(() => transactionsApi.categories(), []);
  const limit = PAGE_SIZE * pages;
  const transactions = useApi(
    () =>
      transactionsApi.list({
        limit,
        kind: filterType === 'all' ? undefined : kindFromKey(filterType),
        category: filterCategory === 'all' ? undefined : filterCategory,
        date_from: dateFrom ? new Date(`${dateFrom}T00:00:00`).toISOString() : undefined,
        date_to: dateTo ? endOfDay(new Date(`${dateTo}T00:00:00`)).toISOString() : undefined,
      }),
    [limit, filterType, filterCategory, dateFrom, dateTo],
  );
  const recurring = useApi(() => recurringApi.list(), []);

  // Free-text search runs locally: the backend has no text search parameter
  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const items = transactions.data ?? [];
    if (!q) return items;
    return items.filter(
      (tx) =>
        tx.name.toLowerCase().includes(q) ||
        tx.category_name.includes(q) ||
        translateCategory(tx.category_name).toLowerCase().includes(q) ||
        (tx.note ?? '').toLowerCase().includes(q) ||
        tx.tags.some((tag) => tag.includes(q)),
    );
  }, [transactions.data, searchQuery, translateCategory]);

  const allCategories = useMemo(() => {
    const c = categories.data;
    if (!c) return [];
    const list = filterType === 'all' ? [...c.expense, ...c.income, ...c.transfer] : c[filterType];
    return [...new Set(list)].sort((a, b) => translateCategory(a).localeCompare(translateCategory(b)));
  }, [categories.data, filterType, translateCategory]);

  const hasFilters = filterType !== 'all' || filterCategory !== 'all' || dateFrom || dateTo || searchQuery;
  const canLoadMore = (transactions.data?.length ?? 0) >= limit && limit < 1000;

  const resetFilters = () => {
    setFilterType('all');
    setFilterCategory('all');
    setDateFrom('');
    setDateTo('');
    setSearchQuery('');
    setPages(1);
  };

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await transactionsApi.remove(deleting.id_);
      toast.success(t.transactions.deleted);
      notifyDataChanged();
      void refreshUser();
    } catch (err) {
      toast.error(errorMessage(err, t));
    }
  };

  const handleExport = () => {
    if (filtered.length === 0) {
      toast.info(t.transactions.exportEmpty);
      return;
    }
    downloadCsv(`transactions-${toDateInput()}.csv`, [
      ['date', 'name', 'kind', 'category_name', 'amount', 'currency', 'tags', 'note'],
      ...filtered.map((tx) => [
        toDateInput(tx.date),
        tx.name,
        kindKey(tx.kind).toUpperCase(),
        tx.category_name,
        tx.amount,
        tx.currency ?? '',
        tx.tags.join('|'),
        tx.note ?? '',
      ]),
    ]);
  };

  const handleImport = async () => {
    const file = importFile;
    if (!file) return;
    setImporting(true);
    try {
      const result = await transactionsApi.import(file);
      toast.success(fmt(t.transactions.importResult, { imported: result.imported, skipped: result.skipped }));
      if (result.errors.length) toast.warning(result.errors.slice(0, 3).join('\n'));
      setImportOpen(false);
      notifyDataChanged();
      void refreshUser();
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setImporting(false);
    }
  };

  const toggleRecurring = async (rule: RecurringOut) => {
    try {
      await recurringApi.update(rule.id_, { is_active: !rule.is_active });
      toast.success(t.transactions.recurringUpdated);
      recurring.reload();
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
            onClick={() => {
              setImportFile(null);
              setImportOpen(true);
            }}
          >
            <Upload className="w-4 h-4 mr-2" />
            {t.transactions.import}
          </Button>
          <Button variant="outline" size="sm" onClick={handleExport}>
            <Download className="w-4 h-4 mr-2" />
            {t.transactions.export}
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
                placeholder={t.transactions.searchPlaceholder}
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
              {t.transactions.from}
              <Input type="date" className="w-[160px]" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </label>
            <label className="flex items-center gap-2 text-gray-600">
              {t.transactions.to}
              <Input type="date" className="w-[160px]" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </label>
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
        <CardHeader>
          <CardTitle>{fmt(t.transactions.count, { count: filtered.length })}</CardTitle>
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
                            <h4 className="font-medium text-gray-900 truncate">{tx.name}</h4>
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
                              <DropdownMenuItem className="text-red-600" onClick={() => setDeleting(tx)}>
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
        <CardHeader>
          <div className="flex items-center gap-2">
            <Repeat className="w-5 h-5 text-blue-600" />
            <CardTitle>{t.transactions.recurring}</CardTitle>
          </div>
          <p className="text-xs text-gray-500">{t.transactions.recurringHint}</p>
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

      <TransactionFormDialog open={formOpen} onOpenChange={setFormOpen} categories={categories.data} transaction={editing} />

      <ConfirmDialog
        open={Boolean(deleting)}
        onOpenChange={(open) => !open && setDeleting(null)}
        description={deleting ? fmt(t.transactions.deleteConfirm, { name: deleting.name }) : undefined}
        onConfirm={handleDelete}
      />
      <ConfirmDialog
        open={Boolean(deletingRecurring)}
        onOpenChange={(open) => !open && setDeletingRecurring(null)}
        description={deletingRecurring ? fmt(t.transactions.deleteConfirm, { name: deletingRecurring.name }) : undefined}
        onConfirm={deleteRecurring}
      />

      {/* Import */}
      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t.transactions.importTitle}</DialogTitle>
            <DialogDescription>{t.transactions.importDescription}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => setImportFile(e.target.files?.[0] ?? null)} />
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setImportOpen(false)}>
                {t.common.cancel}
              </Button>
              <Button className="flex-1" onClick={handleImport} disabled={importing || !importFile}>
                {importing ? t.transactions.importing : t.transactions.importButton}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
