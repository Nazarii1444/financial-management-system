import { ReactNode } from 'react';
import { AlertTriangle, Inbox, Loader2 } from 'lucide-react';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { useLanguage } from '../../i18n/LanguageContext';
import { errorMessage } from '../../lib/errors';

export function LoadingState({ className = 'py-12' }: { className?: string }) {
  const { t } = useLanguage();
  return (
    <div className={`flex items-center justify-center gap-2 text-sm text-gray-500 ${className}`}>
      <Loader2 className="w-4 h-4 animate-spin" />
      {t.common.loading}
    </div>
  );
}

export function ErrorState({ error, onRetry, className = 'py-10' }: { error: unknown; onRetry?: () => void; className?: string }) {
  const { t } = useLanguage();
  return (
    <div className={`flex flex-col items-center justify-center gap-3 text-center ${className}`}>
      <AlertTriangle className="w-6 h-6 text-orange-500" />
      <p className="text-sm text-gray-600">{errorMessage(error, t)}</p>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry}>
          {t.common.retry}
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ title, action, className = 'py-10' }: { title: string; action?: ReactNode; className?: string }) {
  return (
    <div className={`flex flex-col items-center justify-center gap-3 text-center ${className}`}>
      <Inbox className="w-8 h-8 text-gray-300" />
      <p className="text-sm text-gray-500">{title}</p>
      {action}
    </div>
  );
}

/** Marks UI that has no backend support yet (tracked in docs/INTEGRATION_GAPS.md) */
export function ComingSoonBadge() {
  const { t } = useLanguage();
  return (
    <Badge variant="outline" className="text-[10px] uppercase tracking-wide border-amber-300 text-amber-700 bg-amber-50" title={t.common.comingSoonHint}>
      {t.common.comingSoon}
    </Badge>
  );
}

/** Renders loading / error states and only calls children once data is ready */
export function AsyncBlock<T>({
  state,
  children,
  className,
}: {
  state: { data: T | undefined; loading: boolean; error: unknown; reload: () => void };
  children: (data: T) => ReactNode;
  className?: string;
}) {
  if (state.error && state.data === undefined) return <ErrorState error={state.error} onRetry={state.reload} className={className} />;
  if (state.data === undefined) return <LoadingState className={className} />;
  return <>{children(state.data)}</>;
}
