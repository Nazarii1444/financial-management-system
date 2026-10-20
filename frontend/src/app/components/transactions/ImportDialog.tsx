import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { AlertTriangle, ArrowLeft, Copy, FileUp, Lock } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Switch } from '../ui/switch';
import { Badge } from '../ui/badge';
import { useLanguage } from '../../i18n/LanguageContext';
import { fmt } from '../../i18n/translations';
import { useAuth } from '../../context/AuthContext';
import { notifyDataChanged } from '../../hooks/useApi';
import { ApiError, transactionsApi } from '../../lib/api';
import { errorMessage } from '../../lib/errors';
import { kindFromKey, kindKey, toDateInput, toNumber, type KindKey } from '../../lib/finance';
import type { CategoriesList, StatementPreview, StatementPreviewRow } from '../../types/api';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categories: CategoriesList | undefined;
}

interface EditableRow extends StatementPreviewRow {
  key: number;
  checked: boolean;
}

const selectClass =
  'h-8 rounded-md border border-gray-200 bg-white px-1.5 text-xs text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-200';

/** Upload → preview (edit kind / category, pick rows and period) → import */
export function ImportDialog({ open, onOpenChange, categories }: Props) {
  const { t, translateCategory, formatMoney, formatDate } = useLanguage();
  const { refreshUser } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<StatementPreview | null>(null);
  const [rows, setRows] = useState<EditableRow[]>([]);
  const [periodFrom, setPeriodFrom] = useState('');
  const [periodTo, setPeriodTo] = useState('');
  const [updateBalance, setUpdateBalance] = useState(false);
  // Encrypted exports (.fhx): the server answers "passphrase_required" and the field appears
  const [needsPassphrase, setNeedsPassphrase] = useState(false);
  const [passphrase, setPassphrase] = useState('');

  const chooseFile = (next: File | null) => {
    setFile(next);
    setNeedsPassphrase(false);
    setPassphrase('');
  };

  const reset = () => {
    chooseFile(null);
    setPreview(null);
    setRows([]);
    setUpdateBalance(false);
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  const loadPreview = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const data = await transactionsApi.previewStatement(file, needsPassphrase ? passphrase : undefined);
      setPassphrase('');
      setNeedsPassphrase(false);
      setPreview(data);
      setRows(data.rows.map((r, key) => ({ ...r, key, checked: r.selected })));
      setPeriodFrom(data.period_from ?? '');
      setPeriodTo(data.period_to ?? '');
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : null;
      if (detail === 'passphrase_required') setNeedsPassphrase(true);
      else if (detail === 'wrong_passphrase') toast.error(t.importer.wrongPassphrase);
      else if (detail === 'corrupt_file') toast.error(t.importer.corruptFile);
      else toast.error(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  const inPeriod = (r: EditableRow) => {
    if (!r.date) return true;
    const day = toDateInput(r.date);
    return (!periodFrom || day >= periodFrom) && (!periodTo || day <= periodTo);
  };
  const visible = rows.filter(inPeriod);
  const chosen = visible.filter((r) => r.checked);
  const hidden = rows.length - visible.length;

  const totals = useMemo(() => {
    let expense = 0;
    let income = 0;
    for (const r of chosen) {
      const kind = kindKey(r.kind);
      if (kind === 'expense') expense += toNumber(r.amount);
      if (kind === 'income') income += toNumber(r.amount);
    }
    return { expense, income };
  }, [chosen]);

  const update = (key: number, patch: Partial<EditableRow>) =>
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  const changeKind = (row: EditableRow, kind: KindKey) => {
    const options = categories?.[kind] ?? [];
    const category = options.includes(row.category_name) ? row.category_name : kind === 'transfer' ? 'transfer' : kind === 'income' ? 'other' : 'shopping';
    update(row.key, { kind: kindFromKey(kind), category_name: category });
  };

  const allChecked = visible.length > 0 && visible.every((r) => r.checked);
  const toggleAll = () => {
    const keys = new Set(visible.map((r) => r.key));
    setRows((prev) => prev.map((r) => (keys.has(r.key) ? { ...r, checked: !allChecked } : r)));
  };

  const confirm = async () => {
    if (!preview) return;
    if (chosen.length === 0) {
      toast.error(t.importer.nothingSelected);
      return;
    }
    setBusy(true);
    try {
      const result = await transactionsApi.confirmStatement({
        bank: preview.bank,
        update_balance: updateBalance,
        rows: chosen.map((r) => ({
          ref: r.ref,
          date: r.date ?? new Date().toISOString(),
          name: r.name,
          amount: toNumber(r.amount),
          currency: r.currency,
          kind: r.kind,
          category_name: r.category_name,
          note: r.note,
          tags: r.tags ?? [],
        })),
      });
      toast.success(
        result.skipped_duplicates
          ? fmt(t.importer.doneSkipped, { imported: result.imported, skipped: result.skipped_duplicates })
          : fmt(t.importer.done, { imported: result.imported }),
      );
      if (result.errors.length) toast.warning(result.errors.slice(0, 3).join('\n'));
      handleOpenChange(false);
      notifyDataChanged();
      void refreshUser();
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className={`${preview ? 'sm:max-w-4xl' : 'sm:max-w-md'} max-h-[92vh] overflow-y-auto`}>
        <DialogHeader>
          <DialogTitle>{t.importer.title}</DialogTitle>
          <DialogDescription>{preview ? fmt(t.importer.source, { bank: preview.bank_name, format: preview.file_format.toUpperCase() }) : t.importer.description}</DialogDescription>
        </DialogHeader>

        {!preview ? (
          <div className="space-y-4">
            <p className="text-xs text-gray-500">{t.importer.supported}</p>
            <Input type="file" accept=".pdf,.csv,.xlsx,.xls,.p7s,.fhx" aria-label={t.importer.choose} onChange={(e) => chooseFile(e.target.files?.[0] ?? null)} />
            {needsPassphrase && (
              <div className="space-y-2 rounded-lg border border-blue-100 bg-blue-50 p-3">
                <p className="flex items-center gap-1.5 text-sm text-blue-900">
                  <Lock className="w-4 h-4 shrink-0" />
                  {t.importer.encrypted}
                </p>
                <Input
                  type="password"
                  autoFocus
                  autoComplete="off"
                  aria-label={t.importer.passphrase}
                  placeholder={t.importer.passphrase}
                  value={passphrase}
                  onChange={(e) => setPassphrase(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && passphrase && void loadPreview()}
                />
              </div>
            )}
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => handleOpenChange(false)}>
                {t.common.cancel}
              </Button>
              <Button className="flex-1" onClick={loadPreview} disabled={busy || !file || (needsPassphrase && !passphrase)}>
                <FileUp className="w-4 h-4 mr-2" />
                {busy ? t.importer.reading : t.importer.next}
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="text-gray-600">{t.importer.period}</span>
              <label className="flex items-center gap-2 text-gray-600">
                {t.importer.from}
                <Input type="date" className="w-[150px] h-8" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} />
              </label>
              <label className="flex items-center gap-2 text-gray-600">
                {t.importer.to}
                <Input type="date" className="w-[150px] h-8" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} />
              </label>
              {hidden > 0 && <span className="text-xs text-gray-400">{fmt(t.importer.outsidePeriod, { count: hidden })}</span>}
              {preview.opening_balance !== null && preview.closing_balance !== null && (
                <span className="text-xs text-gray-500 ml-auto">
                  {fmt(t.importer.balanceCheck, {
                    from: formatMoney(toNumber(preview.opening_balance), preview.currency),
                    to: formatMoney(toNumber(preview.closing_balance), preview.currency),
                  })}
                </span>
              )}
            </div>

            <div className="flex items-start gap-3 rounded-lg border border-gray-100 bg-gray-50 p-3">
              <Switch id="import-update-balance" checked={updateBalance} onCheckedChange={setUpdateBalance} />
              <label htmlFor="import-update-balance" className="cursor-pointer">
                <span className="block text-sm font-medium text-gray-900">{t.importer.updateBalance}</span>
                <span className="block text-xs text-gray-500 mt-0.5">{t.importer.updateBalanceHint}</span>
              </label>
            </div>

            {preview.warnings.length > 0 && (
              <p className="flex gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                {preview.warnings.slice(0, 3).join(' · ')}
              </p>
            )}

            <div className="rounded-lg border border-gray-100 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-xs text-gray-500">
                  <tr>
                    <th className="p-2 w-8">
                      <input type="checkbox" aria-label={t.importer.selectAll} checked={allChecked} onChange={toggleAll} />
                    </th>
                    <th className="p-2 text-left font-medium">{t.transactions.date}</th>
                    <th className="p-2 text-left font-medium">{t.transactions.name}</th>
                    <th className="p-2 text-left font-medium">{t.transactions.type}</th>
                    <th className="p-2 text-left font-medium">{t.transactions.category}</th>
                    <th className="p-2 text-right font-medium">{t.transactions.amount}</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((row) => {
                    const kind = kindKey(row.kind);
                    const tone = kind === 'income' ? 'text-green-600' : kind === 'expense' ? 'text-red-600' : 'text-gray-600';
                    return (
                      <tr key={row.key} className={`border-t border-gray-100 ${row.checked ? '' : 'opacity-50'}`}>
                        <td className="p-2 text-center">
                          <input
                            type="checkbox"
                            aria-label={row.name}
                            checked={row.checked}
                            onChange={(e) => update(row.key, { checked: e.target.checked })}
                          />
                        </td>
                        <td className="p-2 whitespace-nowrap text-gray-600">
                          {formatDate(row.date)}
                          {row.date && <span className="block text-xs text-gray-400">{new Date(row.date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>}
                        </td>
                        <td className="p-2 min-w-[180px]">
                          <span className="text-gray-900">{row.name}</span>
                          <div className="flex flex-wrap gap-1 mt-0.5">
                            {row.duplicate && (
                              <Badge variant="outline" className="text-[10px] border-gray-300 text-gray-500">
                                <Copy className="w-3 h-3 mr-1" />
                                {t.importer.duplicate}
                              </Badge>
                            )}
                            {row.similar && (
                              <Badge variant="outline" className="text-[10px] border-amber-300 text-amber-700" title={t.importer.similarHint}>
                                {t.importer.similar}
                              </Badge>
                            )}
                          </div>
                          {row.note && <span className="block text-xs text-gray-400 truncate max-w-[260px]">{row.note}</span>}
                        </td>
                        <td className="p-2">
                          <select className={selectClass} value={kind} aria-label={t.transactions.type} onChange={(e) => changeKind(row, e.target.value as KindKey)}>
                            <option value="expense">{t.kinds.expense}</option>
                            <option value="income">{t.kinds.income}</option>
                            <option value="transfer">{t.kinds.transfer}</option>
                          </select>
                        </td>
                        <td className="p-2">
                          <select
                            className={`${selectClass} max-w-[170px]`}
                            value={row.category_name}
                            aria-label={t.transactions.category}
                            onChange={(e) => update(row.key, { category_name: e.target.value })}
                          >
                            {[...(categories?.[kind] ?? [row.category_name])]
                              .sort((a, b) => translateCategory(a).localeCompare(translateCategory(b)))
                              .map((cat) => (
                                <option key={cat} value={cat}>
                                  {translateCategory(cat)}
                                </option>
                              ))}
                          </select>
                        </td>
                        <td className={`p-2 text-right whitespace-nowrap font-medium ${tone}`}>
                          {kind === 'income' ? '+' : kind === 'expense' ? '−' : ''}
                          {formatMoney(toNumber(row.amount), row.currency)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <p className="text-sm text-gray-600 flex-1" data-testid="import-summary">
                {fmt(t.importer.selected, { selected: chosen.length, total: visible.length })}
                {' · '}
                <span className="text-red-600">{fmt(t.importer.sumExpense, { amount: formatMoney(totals.expense, preview.currency ?? rows[0]?.currency) })}</span>
                {totals.income > 0 && (
                  <>
                    {' · '}
                    <span className="text-green-600">{fmt(t.importer.sumIncome, { amount: formatMoney(totals.income, preview.currency ?? rows[0]?.currency) })}</span>
                  </>
                )}
              </p>
              <Button variant="outline" onClick={reset} disabled={busy}>
                <ArrowLeft className="w-4 h-4 mr-1" />
                {t.importer.back}
              </Button>
              <Button onClick={confirm} disabled={busy || chosen.length === 0}>
                {busy ? t.importer.importing : fmt(t.importer.import, { count: chosen.length })}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
