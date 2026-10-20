import { useState } from 'react';
import { toast } from 'sonner';
import { ArrowDownCircle, ArrowLeftRight, ArrowUpCircle, Receipt, RotateCcw, Trash2 } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { AsyncBlock, EmptyState } from '../common/States';
import { useLanguage } from '../../i18n/LanguageContext';
import { fmt } from '../../i18n/translations';
import { useAuth } from '../../context/AuthContext';
import { notifyDataChanged, useApi } from '../../hooks/useApi';
import { trashApi } from '../../lib/api';
import { errorMessage } from '../../lib/errors';
import { daysUntil, kindKey, toNumber } from '../../lib/finance';
import type { TrashItem } from '../../types/api';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Deleted transactions: restore (balance returns exactly) or delete forever; auto-purged after 30 days */
export function TrashDialog({ open, onOpenChange }: Props) {
  const { t, translateCategory, formatMoney, formatDate } = useLanguage();
  const { user, refreshUser } = useAuth();
  const trash = useApi(() => trashApi.list(), [open], open);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [purging, setPurging] = useState<TrashItem | null>(null);
  const [confirmEmpty, setConfirmEmpty] = useState(false);
  const items = trash.data ?? [];

  const restore = async (item: TrashItem) => {
    setBusyId(item.id_);
    try {
      await trashApi.restore(item.id_);
      toast.success(t.history.restored);
      trash.setData(items.filter((x) => x.id_ !== item.id_));
      notifyDataChanged();
      void refreshUser();
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setBusyId(null);
    }
  };

  const purge = async () => {
    if (!purging) return;
    try {
      await trashApi.purge(purging.id_);
      toast.success(t.history.deletedForever);
      trash.setData(items.filter((x) => x.id_ !== purging.id_));
    } catch (err) {
      toast.error(errorMessage(err, t));
    }
  };

  const empty = async () => {
    try {
      await trashApi.empty();
      toast.success(t.history.trashEmptied);
      trash.setData([]);
    } catch (err) {
      toast.error(errorMessage(err, t));
    }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t.history.trashTitle}</DialogTitle>
            <DialogDescription>{t.history.trashHint}</DialogDescription>
          </DialogHeader>
          <AsyncBlock state={trash}>
            {() =>
              items.length === 0 ? (
                <EmptyState title={t.history.trashEmpty} className="py-6" />
              ) : (
                <div className="space-y-2">
                  {items.map((item) => {
                    const kind = kindKey(item.kind);
                    const Icon = kind === 'income' ? ArrowUpCircle : kind === 'expense' ? ArrowDownCircle : ArrowLeftRight;
                    const tone = kind === 'income' ? 'text-green-600' : kind === 'expense' ? 'text-red-600' : 'text-gray-600';
                    return (
                      <div key={item.id_} className="flex items-center gap-3 p-3 rounded-lg border border-gray-100">
                        <Icon className={`w-5 h-5 shrink-0 ${tone}`} />
                        <div className="min-w-0 flex-1">
                          <p className="font-medium text-gray-900 truncate flex items-center gap-1">
                            {item.name}
                            {item.has_receipt && <Receipt className="w-3.5 h-3.5 text-gray-400" aria-label={t.history.hasReceipt} />}
                          </p>
                          <p className="text-xs text-gray-500">
                            {translateCategory(item.category_name)} · {formatDate(item.date)} · {fmt(t.history.deletedOn, { date: formatDate(item.deleted_at) })}
                          </p>
                        </div>
                        <div className="text-right shrink-0">
                          <p className={`font-semibold whitespace-nowrap ${tone}`}>
                            {kind === 'income' ? '+' : kind === 'expense' ? '−' : ''}
                            {formatMoney(toNumber(item.amount), item.currency || user?.default_currency)}
                          </p>
                          <p className="text-xs text-gray-400">{fmt(t.history.daysLeft, { days: Math.max(0, daysUntil(item.expires_at)) })}</p>
                        </div>
                        <Button size="sm" variant="outline" disabled={busyId === item.id_} onClick={() => restore(item)}>
                          <RotateCcw className="w-3.5 h-3.5 mr-1" />
                          {t.history.restore}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-8 w-8 p-0 text-red-600"
                          title={t.history.deleteForever}
                          aria-label={t.history.deleteForever}
                          onClick={() => setPurging(item)}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    );
                  })}
                  <div className="flex justify-end pt-2">
                    <Button variant="ghost" size="sm" className="text-red-600" onClick={() => setConfirmEmpty(true)}>
                      {t.history.emptyTrash}
                    </Button>
                  </div>
                </div>
              )
            }
          </AsyncBlock>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={Boolean(purging)}
        onOpenChange={(o) => !o && setPurging(null)}
        description={purging ? fmt(t.history.deleteForeverConfirm, { name: purging.name }) : undefined}
        confirmLabel={t.history.deleteForever}
        onConfirm={purge}
      />
      <ConfirmDialog
        open={confirmEmpty}
        onOpenChange={setConfirmEmpty}
        description={fmt(t.history.emptyTrashConfirm, { count: items.length })}
        confirmLabel={t.history.emptyTrash}
        onConfirm={empty}
      />
    </>
  );
}
