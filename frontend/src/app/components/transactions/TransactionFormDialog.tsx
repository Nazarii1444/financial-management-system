import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { useLanguage } from '../../i18n/LanguageContext';
import { useAuth } from '../../context/AuthContext';
import { recurringApi, templatesApi, transactionsApi } from '../../lib/api';
import { errorMessage } from '../../lib/errors';
import { fromDateInput, kindFromKey, kindKey, parseTags, toDateInput, toNumber, type KindKey } from '../../lib/finance';
import { notifyDataChanged } from '../../hooks/useApi';
import { CURRENCIES, type CategoriesList, type RecurringFrequency, type TransactionOut } from '../../types/api';

const FREQUENCIES: RecurringFrequency[] = ['DAILY', 'WEEKLY', 'BIWEEKLY', 'MONTHLY', 'YEARLY'];

/** Next occurrence after `date` — used as first_run so the recurring rule doesn't duplicate today's transaction */
function nextRun(dateInput: string, frequency: RecurringFrequency) {
  const d = new Date(`${dateInput}T12:00:00`);
  if (frequency === 'DAILY') d.setDate(d.getDate() + 1);
  if (frequency === 'WEEKLY') d.setDate(d.getDate() + 7);
  if (frequency === 'BIWEEKLY') d.setDate(d.getDate() + 14);
  if (frequency === 'MONTHLY') d.setMonth(d.getMonth() + 1);
  if (frequency === 'YEARLY') d.setFullYear(d.getFullYear() + 1);
  return d.toISOString();
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categories: CategoriesList | undefined;
  /** Edit mode when set */
  transaction?: TransactionOut | null;
}

export function TransactionFormDialog({ open, onOpenChange, categories, transaction }: Props) {
  const { t, translateCategory } = useLanguage();
  const { user, refreshUser } = useAuth();
  const isEdit = Boolean(transaction);

  const [kind, setKind] = useState<KindKey>('expense');
  const [category, setCategory] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [recurring, setRecurring] = useState(false);
  const [asTemplate, setAsTemplate] = useState(false);
  const [frequency, setFrequency] = useState<RecurringFrequency>('MONTHLY');
  const [saving, setSaving] = useState(false);

  // Reset the form every time the dialog opens
  useEffect(() => {
    if (!open) return;
    setKind(transaction ? kindKey(transaction.kind) : 'expense');
    setCategory(transaction?.category_name ?? '');
    setCurrency(transaction?.currency || user?.default_currency || 'USD');
    setRecurring(false);
    setAsTemplate(false);
    setFrequency('MONTHLY');
  }, [open, transaction, user?.default_currency]);

  const options = categories ? categories[kind] : [];

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    if (!category) {
      toast.error(t.transactions.selectCategory);
      return;
    }
    const date = String(form.get('date'));
    const payload = {
      name: String(form.get('name')).trim(),
      amount: Number(form.get('amount')),
      kind: kindFromKey(kind),
      category_name: category,
      currency,
      date: fromDateInput(date),
      tags: parseTags(String(form.get('tags') ?? '')),
      note: String(form.get('note') ?? '').trim() || null,
    };

    setSaving(true);
    try {
      if (transaction) {
        await transactionsApi.update(transaction.id_, payload);
        toast.success(t.transactions.updated);
      } else {
        await transactionsApi.create(payload);
        if (recurring) {
          const { date: _date, ...rest } = payload;
          await recurringApi.create({ ...rest, frequency, first_run: nextRun(date, frequency) });
        }
        if (asTemplate) {
          const { date: _date, ...rest } = payload;
          await templatesApi.create(rest);
        }
        const extras = [recurring && t.transactions.recurringCreated, asTemplate && t.templates.created].filter(Boolean);
        toast.success([t.transactions.created, ...extras].join('. '));
      }
      onOpenChange(false);
      notifyDataChanged();
      void refreshUser(); // balance (capital) changed on the server
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
          <DialogTitle>{isEdit ? t.transactions.editTransaction : t.transactions.addNewTransaction}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label>{t.transactions.type}</Label>
            <Select
              value={kind}
              onValueChange={(value: KindKey) => {
                setKind(value);
                // A category from another kind would be rejected by the backend
                if (!categories?.[value].includes(category)) setCategory('');
              }}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="expense">{t.kinds.expense}</SelectItem>
                <SelectItem value="income">{t.kinds.income}</SelectItem>
                <SelectItem value="transfer">{t.kinds.transfer}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="tx-name">{t.transactions.name}</Label>
            <Input id="tx-name" name="name" maxLength={64} placeholder={t.transactions.namePlaceholder} defaultValue={transaction?.name} required />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2 col-span-2">
              <Label htmlFor="tx-amount">{t.transactions.amount}</Label>
              <Input
                id="tx-amount"
                name="amount"
                type="number"
                step="0.01"
                min="0.01"
                placeholder="0.00"
                defaultValue={transaction ? toNumber(transaction.amount) : undefined}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>{t.transactions.currency}</Label>
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
            <Label>{t.transactions.category}</Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger>
                <SelectValue placeholder={t.transactions.selectCategory} />
              </SelectTrigger>
              <SelectContent>
                {[...options]
                  .sort((a, b) => translateCategory(a).localeCompare(translateCategory(b)))
                  .map((cat) => (
                    <SelectItem key={cat} value={cat}>
                      {translateCategory(cat)}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="tx-date">{t.transactions.date}</Label>
            <Input id="tx-date" name="date" type="date" defaultValue={toDateInput(transaction?.date ?? new Date())} required />
          </div>
          <div className="space-y-2">
            <Label htmlFor="tx-tags">
              {t.transactions.tags} <span className="text-gray-400 font-normal">({t.common.optional})</span>
            </Label>
            <Input id="tx-tags" name="tags" placeholder={t.transactions.tagsPlaceholder} defaultValue={transaction?.tags.join(', ')} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="tx-note">
              {t.transactions.note} <span className="text-gray-400 font-normal">({t.common.optional})</span>
            </Label>
            <Textarea id="tx-note" name="note" maxLength={512} placeholder={t.transactions.notePlaceholder} defaultValue={transaction?.note ?? ''} />
          </div>
          {!isEdit && (
            <div className="space-y-3 rounded-lg border border-gray-100 p-3">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="tx-recurring"
                  className="rounded"
                  checked={recurring}
                  onChange={(e) => setRecurring(e.target.checked)}
                />
                <Label htmlFor="tx-recurring" className="text-sm cursor-pointer">
                  {t.transactions.recurringTransaction}
                </Label>
              </div>
              {recurring && (
                <div className="space-y-2">
                  <Label>{t.transactions.frequency}</Label>
                  <Select value={frequency} onValueChange={(v: RecurringFrequency) => setFrequency(v)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {FREQUENCIES.map((f) => (
                        <SelectItem key={f} value={f}>
                          {t.frequency[f]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="tx-as-template"
                  className="rounded"
                  checked={asTemplate}
                  onChange={(e) => setAsTemplate(e.target.checked)}
                />
                <Label htmlFor="tx-as-template" className="text-sm cursor-pointer">
                  {t.templates.saveAsTemplate}
                </Label>
              </div>
            </div>
          )}
          <div className="flex gap-3 pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} className="flex-1">
              {t.common.cancel}
            </Button>
            <Button type="submit" className="flex-1" disabled={saving}>
              {saving ? t.common.saving : isEdit ? t.common.save : t.transactions.addTransaction}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
