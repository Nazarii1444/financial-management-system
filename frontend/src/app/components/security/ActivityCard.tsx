import { useState } from 'react';
import { History, Monitor, Smartphone, XCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { AsyncBlock } from '../common/States';
import { useLanguage } from '../../i18n/LanguageContext';
import { fmt } from '../../i18n/translations';
import { useApi } from '../../hooks/useApi';
import { securityApi } from '../../lib/api';
import type { SecurityEvent } from '../../types/api';

const PAGE = 20;

/** SEC-S1: every sign-in, failed attempt and security change on the account. */
export function ActivityCard() {
  const { t, formatDate } = useLanguage();
  const [limit, setLimit] = useState(PAGE);
  const state = useApi(() => securityApi.events(limit), [limit]);
  const tt = t.security;

  const title = (e: SecurityEvent) => {
    const events = tt.events as Record<string, string>;
    if (!e.success && events[`${e.event_type}_failed`]) return events[`${e.event_type}_failed`];
    return events[e.event_type] ?? e.event_type;
  };
  const detail = (e: SecurityEvent) => {
    const parts: string[] = [];
    const methods = tt.methods as Record<string, string>;
    if (e.method && e.event_type === 'login') parts.push(methods[e.method] ?? e.method);
    const d = e.details ?? {};
    if (typeof d.passkey === 'string' || typeof d.name === 'string') parts.push(String(d.passkey ?? d.name));
    if (typeof d.file === 'string') parts.push(String(d.file) + (d.encrypted ? ` (${tt.encrypted})` : ''));
    if (typeof d.to === 'string') parts.push(`→ ${d.to}`);
    return parts.join(' · ');
  };
  const time = (iso: string) => {
    const date = new Date(iso);
    return `${formatDate(date)} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
  };

  return (
    <Card className="border-0 shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <History className="w-5 h-5 text-blue-600" />
          {tt.activityTitle}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-gray-600">{tt.activityHint}</p>
        <AsyncBlock state={state}>
          {(data) => (
            <>
              {data.failed_last_30_days > 0 && (
                <p className="text-sm font-medium text-red-700">{fmt(tt.failedRecently, { count: data.failed_last_30_days })}</p>
              )}
              {data.items.length === 0 ? (
                <p className="text-sm text-gray-500">{tt.noActivity}</p>
              ) : (
                <ul className="divide-y divide-gray-100 rounded-lg border border-gray-100">
                  {data.items.map((e) => {
                    const Icon = !e.success ? XCircle : e.device_type === 'mobile' ? Smartphone : Monitor;
                    const extra = detail(e);
                    return (
                      <li key={e.id_} className={`flex items-start gap-3 p-3 ${e.success ? '' : 'bg-red-50/60'}`}>
                        <Icon className={`w-5 h-5 mt-0.5 shrink-0 ${e.success ? 'text-gray-500' : 'text-red-600'}`} />
                        <div className="flex-1 min-w-0">
                          <p className={`text-sm font-medium ${e.success ? 'text-gray-900' : 'text-red-800'}`}>
                            {title(e)}
                            {extra && <span className="font-normal text-gray-500"> · {extra}</span>}
                          </p>
                          <p className="text-xs text-gray-500 mt-0.5 truncate">
                            {e.device ?? tt.unknownDevice}
                            {e.ip && ` · ${e.ip}`}
                          </p>
                        </div>
                        <time className="text-xs text-gray-500 whitespace-nowrap" dateTime={e.created_at}>{time(e.created_at)}</time>
                      </li>
                    );
                  })}
                </ul>
              )}
              {data.total > data.items.length && (
                <Button size="sm" variant="outline" onClick={() => setLimit((n) => n + PAGE)}>
                  {tt.showMore}
                </Button>
              )}
            </>
          )}
        </AsyncBlock>
      </CardContent>
    </Card>
  );
}
