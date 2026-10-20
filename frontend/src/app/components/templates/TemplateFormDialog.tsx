import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Trash2 } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { useLanguage } from '../../i18n/LanguageContext';
import { fmt } from '../../i18n/translations';
import { useAuth } from '../../context/AuthContext';
import { templatesApi } from '../../lib/api';
import { errorMessage } from '../../lib/errors';
import { kindFromKey, kindKey, parseTags, toNumber, type KindKey } from '../../lib/finance';
import { notifyDataChanged } from '../../hooks/useApi';
import { CURRENCIES, type CategoriesList, type TemplateOut } from '../../types/api';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  categories: CategoriesList | undefined;
  /** Edit mode when set */
  template?: TemplateOut | null;
}

export function TemplateFormDialog({ open, onOpenChange, categories, template }: Props) {
  const { t, translateCategory } = useLanguage();
  const { user } = useAuth();
  const isEdit = Boolean(template);

  const [kind, setKind] = useState<KindKey>('expense');
  const [category, setCategory] = useState('');
  const [currency, setCurrency] = useState('USD');
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!open) return;
    setKind(template ? kindKey(template.kind) : 'expense');
    setCategory(template?.category_name ?? '');
    setCurrency(template?.currency || user?.default_currency || 'USD');
  }, [open, template, user?.default_currency]);

  const options = categories ? categories[kind] : [];

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    if (!category) {
      toast.error(t.transactions.selectCategory);
      return;
    }
    const payload = {
      name: String(form.get('name')).trim(),
      amount: Number(form.get('amount')),
      kind: kindFromKey(kind),
      category_name: category,
      currency,
      tags: parseTags(String(form.get('tags') ?? '')),
      note: String(form.get('note') ?? '').trim() || null,
    };

    setSaving(true);
    try {
      if (template) {
        await templatesApi.update(template.id_, payload);
        toast.success(t.templates.updated);
      } else {
        await templatesApi.create(payload);
        toast.success(t.templates.created);
      }
      onOpenChange(false);
      notifyDataChanged();
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!template) return;
    try {
      await templatesApi.remove(template.id_);
      toast.success(t.templates.deleted);
      onOpenChange(false);
      notifyDataChanged();
    } catch (err) {
      toast.error(errorMessage(err, t));
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{isEdit ? t.templates.editTemplate : t.templates.newTemplate}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label>{t.transactions.type}</Label>
              <Select
                value={kind}
                onValueChange={(value: KindKey) => {
                  setKind(value);
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
              <Label htmlFor="tpl-name">{t.transactions.name}</Label>
              <Input id="tpl-name" name="name" maxLength={64} defaultValue={template?.name} required />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-2 col-span-2">
                <Label htmlFor="tpl-amount">{t.transactions.amount}</Label>
                <Input
                  id="tpl-amount"
                  name="amount"
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="0.00"
                  defaultValue={template ? toNumber(template.amount) : undefined}
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
              <Label htmlFor="tpl-tags">
                {t.transactions.tags} <span className="text-gray-400 font-normal">({t.common.optional})</span>
              </Label>
              <Input id="tpl-tags" name="tags" placeholder={t.transactions.tagsPlaceholder} defaultValue={template?.tags.join(', ')} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="tpl-note">
                {t.transactions.note} <span className="text-gray-400 font-normal">({t.common.optional})</span>
              </Label>
              <Textarea id="tpl-note" name="note" maxLength={512} defaultValue={template?.note ?? ''} />
            </div>
            <div className="flex gap-3 pt-2">
              {isEdit && (
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="text-red-600 hover:text-red-700 shrink-0"
                  aria-label={t.common.delete}
                  onClick={() => setConfirmDelete(true)}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              )}
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} className="flex-1">
                {t.common.cancel}
              </Button>
              <Button type="submit" className="flex-1" disabled={saving}>
                {saving ? t.common.saving : isEdit ? t.common.save : t.common.create}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        description={template ? fmt(t.templates.deleteConfirm, { name: template.name }) : undefined}
        onConfirm={handleDelete}
      />
    </>
  );
}
