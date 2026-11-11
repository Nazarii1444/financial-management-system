import { useState } from 'react';
import { toast } from 'sonner';
import { AlertTriangle, CheckCircle2, KeyRound, ShieldAlert } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/dialog';
import { AsyncBlock } from '../common/States';
import { useLanguage } from '../../i18n/LanguageContext';
import { fmt } from '../../i18n/translations';
import { useApi } from '../../hooks/useApi';
import { securityApi } from '../../lib/api';
import { errorMessage } from '../../lib/errors';
import type { PasswordHealth } from '../../types/api';

const LEVEL_STYLE: Record<PasswordHealth['level'], string> = {
  good: 'bg-green-100 text-green-800',
  fair: 'bg-amber-100 text-amber-800',
  weak: 'bg-red-100 text-red-800',
};

/** SEC-S4: age, strength and leak status of the password + what to do next. */
export function PasswordHealthCard() {
  const { t, formatDate } = useLanguage();
  const state = useApi(() => securityApi.passwordHealth(), []);
  const [checkOpen, setCheckOpen] = useState(false);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const runCheck = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password) return;
    setBusy(true);
    try {
      state.setData(await securityApi.checkPassword(password));
      toast.success(t.security.checkDone);
      setCheckOpen(false);
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setPassword('');
      setBusy(false);
    }
  };

  return (
    <Card className="border-0 shadow-sm">
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="w-5 h-5 text-blue-600" />
          {t.security.healthTitle}
        </CardTitle>
        {state.data && <Badge className={LEVEL_STYLE[state.data.level]}>{t.security.level[state.data.level]}</Badge>}
      </CardHeader>
      <CardContent>
        <AsyncBlock state={state}>
          {(h) => (
            <div className="space-y-3">
              <ul className="space-y-1.5 text-sm">
                <li className="text-gray-700">
                  {h.age_days === null ? t.security.changedUnknown : h.age_days === 0 ? t.security.changedToday : fmt(t.security.changedAgo, { days: h.age_days })}
                </li>
                <li className="text-gray-700">
                  {h.score === null ? t.security.scoreUnknown : fmt(t.security.scoreLine, { level: t.security.strength[h.score] })}
                </li>
                <li className={`flex items-center gap-1.5 ${h.breached ? 'text-red-700 font-medium' : 'text-gray-700'}`}>
                  {h.breached ? <ShieldAlert className="w-4 h-4" /> : h.breached === false ? <CheckCircle2 className="w-4 h-4 text-green-600" /> : null}
                  {h.breached ? t.security.breachedYes : h.breached === false ? t.security.breachedNo : t.security.breachedUnknown}
                  {h.checked_at && <span className="text-xs text-gray-500 font-normal">({fmt(t.security.checkedOn, { date: formatDate(h.checked_at) })})</span>}
                </li>
              </ul>
              {h.recommendations.length > 0 && (
                <ul className="space-y-1.5">
                  {h.recommendations.map((code) => (
                    <li key={code} className="flex gap-2 rounded-md bg-amber-50 border border-amber-100 p-2 text-xs text-amber-900">
                      <AlertTriangle className="w-4 h-4 shrink-0 text-amber-600" />
                      {t.security.recs[code]}
                    </li>
                  ))}
                </ul>
              )}
              <Button size="sm" variant="outline" onClick={() => setCheckOpen(true)}>
                {t.security.checkNow}
              </Button>
            </div>
          )}
        </AsyncBlock>
      </CardContent>

      <Dialog open={checkOpen} onOpenChange={(open) => { setCheckOpen(open); if (!open) setPassword(''); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t.security.checkTitle}</DialogTitle>
            <DialogDescription>{t.security.checkHint}</DialogDescription>
          </DialogHeader>
          <form className="space-y-3" onSubmit={runCheck}>
            <Input type="password" autoComplete="current-password" autoFocus aria-label={t.settings.security.currentPassword}
              placeholder={t.settings.security.currentPassword} value={password} onChange={(e) => setPassword(e.target.value)} />
            <Button type="submit" className="w-full" disabled={busy || !password}>
              {busy ? t.common.loading : t.security.checkNow}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
