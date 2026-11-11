import { useState } from 'react';
import { toast } from 'sonner';
import { Cloud, Fingerprint, Pencil, Plus, Trash2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { AsyncBlock } from '../common/States';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { useLanguage } from '../../i18n/LanguageContext';
import { fmt } from '../../i18n/translations';
import { notifyDataChanged, useApi } from '../../hooks/useApi';
import { ApiError, passkeysApi } from '../../lib/api';
import { errorMessage } from '../../lib/errors';
import { createPasskey, defaultPasskeyName, PasskeyCancelled, passkeysSupported } from '../../lib/webauthn';
import type { Passkey } from '../../types/api';
import type { Translations } from '../../i18n/translations';

/** Error code from /passkeys → translated text */
export function passkeyErrorMessage(err: unknown, t: Translations): string {
  if (err instanceof ApiError && typeof err.detail === 'string' && err.detail in t.security.passkeyErrors) {
    return t.security.passkeyErrors[err.detail as keyof Translations['security']['passkeyErrors']];
  }
  return errorMessage(err, t);
}

/** SEC-A1: register, rename and remove passkeys. */
export function PasskeysCard() {
  const { t, formatDate } = useLanguage();
  const state = useApi(() => passkeysApi.list(), []);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<{ id: number; name: string } | null>(null);
  const [removing, setRemoving] = useState<Passkey | null>(null);
  const supported = passkeysSupported();

  const add = async () => {
    setBusy(true);
    try {
      const options = await passkeysApi.registerOptions();
      const credential = await createPasskey(options.public_key);
      await passkeysApi.register(options.challenge_id, credential, defaultPasskeyName());
      toast.success(t.security.passkeyAdded);
      state.reload();
      notifyDataChanged();   // password health counts passkeys
    } catch (err) {
      if (!(err instanceof PasskeyCancelled)) toast.error(passkeyErrorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  const saveName = async () => {
    if (!editing || !editing.name.trim()) return;
    try {
      await passkeysApi.rename(editing.id, editing.name.trim());
      toast.success(t.security.passkeyRenamed);
      setEditing(null);
      state.reload();
    } catch (err) {
      toast.error(errorMessage(err, t));
    }
  };

  return (
    <Card className="border-0 shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Fingerprint className="w-5 h-5 text-blue-600" />
          {t.security.passkeysTitle}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-gray-600">{t.security.passkeysHint}</p>
        <AsyncBlock state={state}>
          {(passkeys) =>
            passkeys.length === 0 ? (
              <p className="text-sm text-gray-500">{t.security.noPasskeys}</p>
            ) : (
              <ul className="divide-y divide-gray-100 rounded-lg border border-gray-100">
                {passkeys.map((p) => (
                  <li key={p.id_} className="flex items-center gap-3 p-3">
                    <Fingerprint className="w-5 h-5 text-gray-500 shrink-0" />
                    <div className="flex-1 min-w-0">
                      {editing?.id === p.id_ ? (
                        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void saveName(); }}>
                          <Input className="h-8" maxLength={64} autoFocus value={editing.name} aria-label={t.security.rename}
                            onChange={(e) => setEditing({ id: p.id_, name: e.target.value })} />
                          <Button type="submit" size="sm">{t.common.save}</Button>
                          <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(null)}>{t.common.cancel}</Button>
                        </form>
                      ) : (
                        <p className="flex items-center gap-2 text-sm font-medium text-gray-900 truncate">
                          {p.name}
                          {p.backed_up && (
                            <Badge variant="secondary" className="gap-1" title={t.security.syncedHint}>
                              <Cloud className="w-3 h-3" />
                              {t.security.synced}
                            </Badge>
                          )}
                        </p>
                      )}
                      <p className="text-xs text-gray-500 mt-0.5">
                        {fmt(t.security.createdOn, { date: formatDate(p.created_at) })} ·{' '}
                        {p.last_used_at ? fmt(t.security.lastUsed, { date: formatDate(p.last_used_at) }) : t.security.neverUsed}
                      </p>
                    </div>
                    {editing?.id !== p.id_ && (
                      <>
                        <Button size="icon" variant="ghost" aria-label={t.security.rename} onClick={() => setEditing({ id: p.id_, name: p.name })}>
                          <Pencil className="w-4 h-4" />
                        </Button>
                        <Button size="icon" variant="ghost" aria-label={t.common.delete} onClick={() => setRemoving(p)}>
                          <Trash2 className="w-4 h-4 text-red-600" />
                        </Button>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )
          }
        </AsyncBlock>
        {supported ? (
          <Button onClick={add} disabled={busy}>
            <Plus className="w-4 h-4 mr-2" />
            {busy ? t.common.loading : t.security.addPasskey}
          </Button>
        ) : (
          <p className="text-sm text-amber-700">{t.security.unsupported}</p>
        )}
      </CardContent>

      <ConfirmDialog
        open={Boolean(removing)}
        onOpenChange={(open) => !open && setRemoving(null)}
        title={t.security.removePasskeyTitle}
        description={removing ? fmt(t.security.removePasskeyText, { name: removing.name }) : undefined}
        confirmLabel={t.common.delete}
        onConfirm={async () => {
          if (!removing) return;
          try {
            await passkeysApi.remove(removing.id_);
            toast.success(t.security.passkeyRemoved);
            setRemoving(null);
            state.reload();
            notifyDataChanged();
          } catch (err) {
            toast.error(errorMessage(err, t));
          }
        }}
      />
    </Card>
  );
}
