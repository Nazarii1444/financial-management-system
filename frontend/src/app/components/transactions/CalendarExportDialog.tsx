import { useState } from 'react';
import { toast } from 'sonner';
import { AlertTriangle, CalendarPlus, Copy, Download, ExternalLink, RefreshCw, Unlink } from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { AsyncBlock } from '../common/States';
import { useLanguage } from '../../i18n/LanguageContext';
import { fmt } from '../../i18n/translations';
import { useApi } from '../../hooks/useApi';
import { calendarApi } from '../../lib/api';
import { errorMessage } from '../../lib/errors';
import type { CalendarFeedOut } from '../../types/api';

export type CalendarTab = 'file' | 'apple' | 'google';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  activeRules: number;
  initialTab?: CalendarTab;
}

const isLocalUrl = (url: string | null) => !!url && /:\/\/(localhost|127\.0\.0\.1|\[::1\])[:/]/.test(url);

/** Export recurring rules: one-off .ics, subscription link (iPhone / Apple / Google by URL) or Google Calendar API sync */
export function CalendarExportDialog({ open, onOpenChange, activeRules, initialTab = 'file' }: Props) {
  const { t } = useLanguage();
  const [tab, setTab] = useState<CalendarTab>(initialTab);
  const [lastInitial, setLastInitial] = useState(initialTab);
  if (initialTab !== lastInitial) {
    setLastInitial(initialTab);
    setTab(initialTab);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t.calendar.title}</DialogTitle>
          <DialogDescription>{t.calendar.description}</DialogDescription>
        </DialogHeader>
        {activeRules === 0 && (
          <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-2">{t.calendar.noRules}</p>
        )}
        <Tabs value={tab} onValueChange={(v) => setTab(v as CalendarTab)}>
          <TabsList className="grid grid-cols-3 w-full">
            <TabsTrigger value="file">{t.calendar.tabFile}</TabsTrigger>
            <TabsTrigger value="apple">{t.calendar.tabApple}</TabsTrigger>
            <TabsTrigger value="google">{t.calendar.tabGoogle}</TabsTrigger>
          </TabsList>
          <TabsContent value="file" className="pt-3">
            <FileTab />
          </TabsContent>
          <TabsContent value="apple" className="pt-3">
            {open && <AppleTab />}
          </TabsContent>
          <TabsContent value="google" className="pt-3">
            {open && <GoogleTab />}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

function FileTab() {
  const { t, language } = useLanguage();
  const [busy, setBusy] = useState(false);

  const download = async () => {
    setBusy(true);
    try {
      const text = await calendarApi.downloadIcs(language);
      const url = URL.createObjectURL(new Blob([text], { type: 'text/calendar;charset=utf-8' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'financehub-payments.ics';
      a.click();
      URL.revokeObjectURL(url);
      toast.success(t.calendar.downloaded);
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3 text-sm text-gray-700">
      <p>{t.calendar.fileHint}</p>
      <p className="text-gray-500">{t.calendar.fileHowTo}</p>
      <Button onClick={download} disabled={busy}>
        <Download className="w-4 h-4 mr-2" />
        {t.calendar.download}
      </Button>
    </div>
  );
}

/** Subscription link block, shared by the Apple tab and the Google "not configured" fallback */
function useFeed() {
  const { t, language } = useLanguage();
  const feed = useApi(() => calendarApi.feed(), []);
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<CalendarFeedOut | void>, success?: string) => {
    setBusy(true);
    try {
      const result = await action();
      feed.setData(result ?? { active: false, url: null, webcal_url: null, google_add_url: null, qr_code_base64: null, lang: null, created_at: null });
      if (success) toast.success(success);
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  return {
    feed,
    busy,
    create: () => run(() => calendarApi.createFeed(language)),
    rotate: () => run(() => calendarApi.createFeed(language, true)),
    revoke: () => run(() => calendarApi.revokeFeed(), t.calendar.revoked),
  };
}

function CopyField({ value }: { value: string }) {
  const { t } = useLanguage();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(t.calendar.copied);
    } catch {
      // Clipboard blocked — the field is selectable anyway
    }
  };
  return (
    <div className="flex gap-2">
      <Input readOnly value={value} onFocus={(e) => e.currentTarget.select()} className="font-mono text-xs" />
      <Button type="button" variant="outline" size="icon" onClick={copy} aria-label={t.calendar.copyLink} title={t.calendar.copyLink}>
        <Copy className="w-4 h-4" />
      </Button>
    </div>
  );
}

function AppleTab() {
  const { t } = useLanguage();
  const { feed, busy, create, rotate, revoke } = useFeed();
  const [confirmRotate, setConfirmRotate] = useState(false);

  return (
    <div className="space-y-3 text-sm text-gray-700">
      <p>{t.calendar.appleHint}</p>
      <AsyncBlock state={feed}>
        {(data) =>
          !data.active || !data.url ? (
            <Button onClick={create} disabled={busy}>
              <CalendarPlus className="w-4 h-4 mr-2" />
              {t.calendar.createLink}
            </Button>
          ) : (
            <div className="space-y-3">
              {isLocalUrl(data.url) && (
                <p className="flex gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  {t.calendar.localhostWarning}
                </p>
              )}
              <Button asChild>
                <a href={data.webcal_url ?? data.url}>
                  <CalendarPlus className="w-4 h-4 mr-2" />
                  {t.calendar.openInCalendar}
                </a>
              </Button>
              <CopyField value={data.url} />
              {data.qr_code_base64 && (
                <div className="flex items-center gap-4">
                  <img
                    src={`data:image/png;base64,${data.qr_code_base64}`}
                    alt={t.calendar.scanQr}
                    className="w-32 h-32 rounded border border-gray-200"
                  />
                  <p className="text-xs text-gray-500">{t.calendar.scanQr}</p>
                </div>
              )}
              <p className="text-xs text-gray-500">{t.calendar.appleManual}</p>
              <p className="text-xs text-gray-500">{t.calendar.secretWarning}</p>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setConfirmRotate(true)} disabled={busy}>
                  <RefreshCw className="w-3.5 h-3.5 mr-1" />
                  {t.calendar.rotate}
                </Button>
                <Button variant="ghost" size="sm" className="text-red-600" onClick={revoke} disabled={busy}>
                  {t.calendar.revoke}
                </Button>
              </div>
            </div>
          )
        }
      </AsyncBlock>
      <ConfirmDialog
        open={confirmRotate}
        onOpenChange={setConfirmRotate}
        title={t.calendar.rotate}
        description={t.calendar.rotateConfirm}
        confirmLabel={t.calendar.rotate}
        destructive={false}
        onConfirm={rotate}
      />
    </div>
  );
}

function GoogleTab() {
  const { t, language, formatDate } = useLanguage();
  const status = useApi(() => calendarApi.googleStatus(), []);
  const [busy, setBusy] = useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);

  const connect = async () => {
    setBusy(true);
    try {
      const { auth_url } = await calendarApi.googleConnect(language);
      window.location.assign(auth_url);
    } catch (err) {
      toast.error(errorMessage(err, t));
      setBusy(false);
    }
  };

  const sync = async () => {
    setBusy(true);
    try {
      const result = await calendarApi.googleSync();
      toast.success(fmt(t.calendar.synced, { count: result.synced }));
      status.reload();
    } catch (err) {
      toast.error(errorMessage(err, t));
      status.reload();
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    try {
      await calendarApi.googleDisconnect();
      toast.success(t.calendar.disconnected);
      status.reload();
    } catch (err) {
      toast.error(errorMessage(err, t));
    }
  };

  return (
    <div className="space-y-3 text-sm text-gray-700">
      <p>{t.calendar.googleHint}</p>
      <AsyncBlock state={status}>
        {(data) =>
          !data.configured && !data.connected ? (
            <GoogleByUrl />
          ) : !data.connected ? (
            <Button onClick={connect} disabled={busy}>
              <CalendarPlus className="w-4 h-4 mr-2" />
              {t.calendar.connect}
            </Button>
          ) : (
            <div className="space-y-3">
              <p className="text-gray-600">
                {data.last_synced_at
                  ? fmt(t.calendar.lastSynced, { date: `${formatDate(data.last_synced_at)} ${new Date(data.last_synced_at).toLocaleTimeString(language, { hour: '2-digit', minute: '2-digit' })}` })
                  : t.calendar.neverSynced}
              </p>
              {data.last_error && (
                <p className="flex gap-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded-md p-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  {data.last_error}
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <Button onClick={sync} disabled={busy}>
                  <RefreshCw className={`w-4 h-4 mr-2 ${busy ? 'animate-spin' : ''}`} />
                  {t.calendar.syncNow}
                </Button>
                {data.calendar_url && (
                  <Button variant="outline" asChild>
                    <a href={data.calendar_url} target="_blank" rel="noreferrer">
                      <ExternalLink className="w-4 h-4 mr-2" />
                      {t.calendar.openGoogle}
                    </a>
                  </Button>
                )}
                <Button variant="ghost" className="text-red-600" onClick={() => setConfirmDisconnect(true)}>
                  <Unlink className="w-4 h-4 mr-2" />
                  {t.calendar.disconnect}
                </Button>
              </div>
            </div>
          )
        }
      </AsyncBlock>
      <ConfirmDialog
        open={confirmDisconnect}
        onOpenChange={setConfirmDisconnect}
        title={t.calendar.disconnect}
        description={t.calendar.disconnectConfirm}
        confirmLabel={t.calendar.disconnect}
        onConfirm={disconnect}
      />
    </div>
  );
}

/** Fallback when the server has no Google OAuth client: subscribe to the feed from Google Calendar */
function GoogleByUrl() {
  const { t } = useLanguage();
  const { feed, busy, create } = useFeed();
  return (
    <div className="space-y-3">
      <p className="text-gray-500">{t.calendar.googleNotConfigured}</p>
      <AsyncBlock state={feed}>
        {(data) =>
          !data.active || !data.google_add_url || !data.url ? (
            <Button variant="outline" onClick={create} disabled={busy}>
              <CalendarPlus className="w-4 h-4 mr-2" />
              {t.calendar.createLink}
            </Button>
          ) : (
            <div className="space-y-2">
              {isLocalUrl(data.url) && (
                <p className="flex gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  {t.calendar.localhostWarning}
                </p>
              )}
              <Button variant="outline" asChild>
                <a href={data.google_add_url} target="_blank" rel="noreferrer">
                  <ExternalLink className="w-4 h-4 mr-2" />
                  {t.calendar.googleAddByUrl}
                </a>
              </Button>
              <CopyField value={data.url} />
            </div>
          )
        }
      </AsyncBlock>
    </div>
  );
}
