import { useState } from 'react';
import { toast } from 'sonner';
import { ChevronDown, Lightbulb, Pencil, Plus, Zap } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover';
import { AsyncBlock } from '../common/States';
import { TemplateFormDialog } from './TemplateFormDialog';
import { useLanguage } from '../../i18n/LanguageContext';
import { fmt } from '../../i18n/translations';
import { useAuth } from '../../context/AuthContext';
import { notifyDataChanged, useApi } from '../../hooks/useApi';
import { templatesApi, transactionsApi, trashApi } from '../../lib/api';
import { errorMessage } from '../../lib/errors';
import { kindKey, toNumber } from '../../lib/finance';
import type { CategoriesList, TemplateOut, TemplateSuggestion, TemplateUseInput } from '../../types/api';

/** Dashboard card: one-click template buttons + "make a template" suggestions */
export function QuickTemplates({ categories }: { categories: CategoriesList | undefined }) {
  const { t, formatMoney } = useLanguage();
  const { refreshUser } = useAuth();
  const templates = useApi(() => templatesApi.list(), []);
  const suggestions = useApi(() => templatesApi.suggestions(), []);

  const [busyId, setBusyId] = useState<number | null>(null);
  const [popoverId, setPopoverId] = useState<number | null>(null);
  const [amount, setAmount] = useState('');
  const [remember, setRemember] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<TemplateOut | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const afterChange = () => {
    notifyDataChanged();
    void refreshUser(); // balance (capital) changed on the server
  };

  const applyTemplate = async (tpl: TemplateOut, input: TemplateUseInput = {}) => {
    if (busyId !== null) return;
    setBusyId(tpl.id_);
    try {
      const tx = await templatesApi.use(tpl.id_, input);
      setPopoverId(null);
      const sign = kindKey(tx.kind) === 'income' ? '+' : kindKey(tx.kind) === 'expense' ? '−' : '';
      toast.success(fmt(t.templates.added, { name: tx.name, amount: sign + formatMoney(toNumber(tx.amount), tx.currency) }), {
        action: {
          label: t.templates.undo,
          onClick: async () => {
            try {
              // An undone click shouldn't linger in the trash
              const deleted = await transactionsApi.remove(tx.id_);
              await trashApi.purge(deleted.trash_id);
              toast.success(t.templates.undone);
              afterChange();
            } catch (err) {
              toast.error(errorMessage(err, t));
            }
          },
        },
      });
      afterChange();
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setBusyId(null);
    }
  };

  const openPopover = (tpl: TemplateOut, open: boolean) => {
    setPopoverId(open ? tpl.id_ : null);
    if (open) {
      setAmount(String(toNumber(tpl.amount)));
      setRemember(false);
    }
  };

  const submitCustom = (tpl: TemplateOut) => (e: React.FormEvent) => {
    e.preventDefault();
    const value = Number(amount);
    if (!Number.isFinite(value) || value <= 0) return;
    const changed = value !== toNumber(tpl.amount);
    void applyTemplate(tpl, changed ? { amount: value, remember_amount: remember } : {});
  };

  const acceptSuggestion = async (s: TemplateSuggestion) => {
    setBusyKey(s.key);
    try {
      await templatesApi.create({
        name: s.name,
        amount: toNumber(s.amount),
        kind: s.kind,
        category_name: s.category_name,
        currency: s.currency,
      });
      toast.success(t.templates.created);
      notifyDataChanged();
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setBusyKey(null);
    }
  };

  const dismissSuggestion = async (s: TemplateSuggestion) => {
    setBusyKey(s.key);
    try {
      await templatesApi.dismissSuggestion(s.key);
      suggestions.setData((suggestions.data ?? []).filter((x) => x.key !== s.key));
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setBusyKey(null);
    }
  };

  const openForm = (tpl: TemplateOut | null) => {
    setPopoverId(null);
    setEditing(tpl);
    setFormOpen(true);
  };

  return (
    <Card className="border-0 shadow-sm">
      <CardHeader className="flex flex-row items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-500" />
            <CardTitle>{t.templates.title}</CardTitle>
          </div>
          <p className="text-xs text-gray-500 mt-1">{t.templates.hint}</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => openForm(null)}>
          <Plus className="w-4 h-4 mr-1" />
          {t.templates.add}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {(suggestions.data ?? []).map((s) => (
          <div
            key={s.key}
            className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3"
          >
            <Lightbulb className="w-5 h-5 text-amber-600 shrink-0" aria-label={t.templates.suggestionTitle} />
            <p className="text-sm text-gray-800 flex-1">
              {fmt(t.templates.suggestion, {
                name: s.name,
                count: s.count,
                amount: formatMoney(toNumber(s.amount), s.currency),
              })}
            </p>
            <div className="flex gap-2 shrink-0">
              <Button size="sm" disabled={busyKey === s.key} onClick={() => acceptSuggestion(s)}>
                {t.templates.accept}
              </Button>
              <Button size="sm" variant="ghost" disabled={busyKey === s.key} onClick={() => dismissSuggestion(s)}>
                {t.templates.dismiss}
              </Button>
            </div>
          </div>
        ))}

        <AsyncBlock state={templates}>
          {(items) =>
            items.length === 0 ? (
              <p className="text-sm text-gray-500">{t.templates.empty}</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {items.map((tpl) => {
                  const kind = kindKey(tpl.kind);
                  const tone =
                    kind === 'income' ? 'text-green-600' : kind === 'expense' ? 'text-red-600' : 'text-gray-600';
                  return (
                    <div
                      key={tpl.id_}
                      className="inline-flex items-stretch rounded-lg border border-gray-200 bg-white shadow-xs overflow-hidden"
                    >
                      <button
                        type="button"
                        className="px-3 py-2 text-left hover:bg-gray-50 disabled:opacity-60 transition-colors"
                        disabled={busyId !== null}
                        onClick={() => applyTemplate(tpl)}
                        title={tpl.use_count ? fmt(t.templates.usedTimes, { count: tpl.use_count }) : undefined}
                      >
                        <span className="block text-sm font-medium text-gray-900">{tpl.name}</span>
                        <span className={`block text-xs ${tone}`}>{formatMoney(toNumber(tpl.amount), tpl.currency)}</span>
                      </button>
                      <Popover open={popoverId === tpl.id_} onOpenChange={(open) => openPopover(tpl, open)}>
                        <PopoverTrigger asChild>
                          <button
                            type="button"
                            className="px-2 border-l border-gray-200 text-gray-500 hover:bg-gray-50"
                            aria-label={`${t.templates.changeAmount}: ${tpl.name}`}
                          >
                            <ChevronDown className="w-4 h-4" />
                          </button>
                        </PopoverTrigger>
                        <PopoverContent align="start" className="w-64 bg-white">
                          <form onSubmit={submitCustom(tpl)} className="space-y-3">
                            <div className="space-y-2">
                              <Label htmlFor={`tpl-use-${tpl.id_}`}>
                                {t.templates.amountForToday} ({tpl.currency})
                              </Label>
                              <Input
                                id={`tpl-use-${tpl.id_}`}
                                type="number"
                                step="0.01"
                                min="0.01"
                                value={amount}
                                onChange={(e) => setAmount(e.target.value)}
                                autoFocus
                                required
                              />
                            </div>
                            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                              <input
                                type="checkbox"
                                className="rounded"
                                checked={remember}
                                onChange={(e) => setRemember(e.target.checked)}
                              />
                              {t.templates.rememberAmount}
                            </label>
                            <div className="flex gap-2">
                              <Button type="button" variant="outline" size="sm" onClick={() => openForm(tpl)}>
                                <Pencil className="w-3.5 h-3.5 mr-1" />
                                {t.common.edit}
                              </Button>
                              <Button type="submit" size="sm" className="flex-1" disabled={busyId !== null}>
                                {t.templates.addNow}
                              </Button>
                            </div>
                          </form>
                        </PopoverContent>
                      </Popover>
                    </div>
                  );
                })}
              </div>
            )
          }
        </AsyncBlock>
      </CardContent>
      <TemplateFormDialog open={formOpen} onOpenChange={setFormOpen} categories={categories} template={editing} />
    </Card>
  );
}
