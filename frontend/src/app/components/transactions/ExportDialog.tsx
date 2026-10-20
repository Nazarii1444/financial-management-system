import { useState } from 'react';
import { toast } from 'sonner';
import { FileSpreadsheet, FileText, Lock, PieChart, Repeat, Target } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { useLanguage } from '../../i18n/LanguageContext';
import { fmt } from '../../i18n/translations';
import { exportsApi, type SearchFilters } from '../../lib/api';
import { errorMessage } from '../../lib/errors';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filters: SearchFilters;
  matchCount: number;
  /** YYYY-MM preselected for monthly reports (the month filter, else the current month) */
  month: string;
}

export function ExportDialog({ open, onOpenChange, filters, matchCount, month: initialMonth }: Props) {
  const { t, language } = useLanguage();
  const [month, setMonth] = useState(initialMonth);
  const [busy, setBusy] = useState<string | null>(null);
  const [encrypt, setEncrypt] = useState(false);
  const [passphrase, setPassphrase] = useState('');
  const [confirmPassphrase, setConfirmPassphrase] = useState('');
  const [lastOpen, setLastOpen] = useState(open);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) setMonth(initialMonth);
    // Never keep a passphrase around between openings
    setEncrypt(false);
    setPassphrase('');
    setConfirmPassphrase('');
  }

  const passphraseError = !encrypt
    ? null
    : passphrase.length < 8
      ? t.history.passphraseShort
      : passphrase !== confirmPassphrase
        ? t.history.passphraseMismatch
        : null;
  const secret = encrypt ? passphrase : undefined;

  const run = async (key: string, action: () => Promise<void>) => {
    setBusy(key);
    try {
      await action();
      toast.success(t.history.downloaded);
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setBusy(null);
    }
  };

  const reports = [
    { key: 'statement', icon: FileText, title: t.history.statement, hint: t.history.statementHint, run: () => exportsApi.statementPdf(month, language, secret) },
    { key: 'expenses', icon: PieChart, title: t.history.expenses, hint: t.history.expensesHint, run: () => exportsApi.expensesPdf(month, language, secret) },
    { key: 'budgets', icon: Target, title: t.history.budgets, hint: t.history.budgetsHint, run: () => exportsApi.budgetsPdf(month, language, secret) },
    { key: 'recurring', icon: Repeat, title: t.history.recurring, hint: t.history.recurringHint, run: () => exportsApi.recurringPdf(language, secret) },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t.history.exportTitle}</DialogTitle>
        </DialogHeader>

        <section className="space-y-3 rounded-lg border border-gray-100 bg-gray-50 p-4">
          <div className="flex items-start gap-3">
            <Switch id="export-encrypt" checked={encrypt} onCheckedChange={setEncrypt} />
            <label htmlFor="export-encrypt" className="cursor-pointer">
              <span className="flex items-center gap-1.5 text-sm font-medium text-gray-900">
                <Lock className="w-4 h-4 text-gray-500" />
                {t.history.encrypt}
              </span>
              <span className="block text-xs text-gray-500 mt-0.5">{t.history.encryptHint}</span>
            </label>
          </div>
          {encrypt && (
            <div className="space-y-2">
              <div className="grid gap-2 sm:grid-cols-2">
                <Input
                  type="password"
                  autoComplete="new-password"
                  aria-label={t.history.passphrase}
                  placeholder={t.history.passphrase}
                  value={passphrase}
                  onChange={(e) => setPassphrase(e.target.value)}
                />
                <Input
                  type="password"
                  autoComplete="new-password"
                  aria-label={t.history.passphraseConfirm}
                  placeholder={t.history.passphraseConfirm}
                  value={confirmPassphrase}
                  onChange={(e) => setConfirmPassphrase(e.target.value)}
                />
              </div>
              {passphraseError && (passphrase || confirmPassphrase) && <p className="text-xs text-red-600">{passphraseError}</p>}
              <p className="text-xs text-amber-700">{t.history.passphraseWarning}</p>
            </div>
          )}
        </section>

        <section className="space-y-2 rounded-lg border border-gray-100 p-4">
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="w-5 h-5 text-green-600" />
            <h3 className="font-medium text-gray-900">{t.history.csvTitle}</h3>
          </div>
          <p className="text-sm text-gray-600">{fmt(t.history.csvHint, { count: matchCount })}</p>
          <Button
            size="sm"
            disabled={busy !== null || matchCount === 0 || passphraseError !== null}
            onClick={() => run('csv', () => exportsApi.transactionsCsv(filters, language, secret))}
          >
            {encrypt && <Lock className="w-4 h-4 mr-1.5" />}
            {t.history.downloadCsv}
          </Button>
        </section>

        <section className="space-y-3 rounded-lg border border-gray-100 p-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <h3 className="font-medium text-gray-900">{t.history.pdfTitle}</h3>
            <div className="flex items-center gap-2">
              <Label htmlFor="report-month" className="text-sm text-gray-600">
                {t.history.reportMonth}
              </Label>
              <Input id="report-month" type="month" className="w-[160px]" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
            </div>
          </div>
          <div className="space-y-2">
            {reports.map((r) => (
              <div key={r.key} className="flex items-center gap-3 rounded-md p-2 hover:bg-gray-50">
                <r.icon className="w-5 h-5 text-blue-600 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">{r.title}</p>
                  <p className="text-xs text-gray-500">{r.hint}</p>
                </div>
                <Button size="sm" variant="outline" disabled={busy !== null || passphraseError !== null} onClick={() => run(r.key, r.run)}>
                  {encrypt && <Lock className="w-3.5 h-3.5 mr-1" />}
                  {busy === r.key ? t.common.loading : 'PDF'}
                </Button>
              </div>
            ))}
          </div>
        </section>
      </DialogContent>
    </Dialog>
  );
}
