import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { User, Bell, Lock, CreditCard, Palette, Globe, Check, X, ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';
import { motion } from 'motion/react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Avatar, AvatarFallback, AvatarImage } from '../components/ui/avatar';
import { Badge } from '../components/ui/badge';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { InputOTP, InputOTPGroup, InputOTPSlot } from '../components/ui/input-otp';
import { useLanguage, DATE_FORMATS, type DateFormat } from '../i18n/LanguageContext';
import type { Language } from '../i18n/translations';
import { useAuth } from '../context/AuthContext';
import { notifyDataChanged, useApi } from '../hooks/useApi';
import { authApi, settingsApi, twoFaApi, usersApi } from '../lib/api';
import { errorMessage } from '../lib/errors';
import { AsyncBlock, ComingSoonBadge } from '../components/common/States';
import { ConfirmDialog } from '../components/common/ConfirmDialog';
import { CURRENCIES, type NotificationPreferences, type TwoFASetup } from '../types/api';
import { PasswordStrengthMeter } from '../components/security/PasswordStrengthMeter';
import { PasswordHealthCard } from '../components/security/PasswordHealthCard';
import { PasskeysCard } from '../components/security/PasskeysCard';
import { ActivityCard } from '../components/security/ActivityCard';

type Tab = 'profile' | 'notifications' | 'security' | 'subscription' | 'preferences';
const TABS: Tab[] = ['profile', 'notifications', 'security', 'subscription', 'preferences'];

export function Settings() {
  const { t } = useLanguage();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab') as Tab | null;
  const activeTab: Tab = tabParam && TABS.includes(tabParam) ? tabParam : 'profile';

  const tabs = [
    { id: 'profile' as const, label: t.settings.tabs.profile, icon: User },
    { id: 'notifications' as const, label: t.settings.tabs.notifications, icon: Bell },
    { id: 'security' as const, label: t.settings.tabs.security, icon: Lock },
    { id: 'subscription' as const, label: t.settings.tabs.subscription, icon: CreditCard },
    { id: 'preferences' as const, label: t.settings.tabs.preferences, icon: Palette },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">{t.settings.title}</h1>
        <p className="text-sm text-gray-500 mt-1">{t.settings.subtitle}</p>
      </div>

      {/* Tab Selector */}
      <div className="relative">
        <div className="relative flex gap-2 p-2 bg-gradient-to-br from-white/90 via-gray-50/80 to-gray-100/90 rounded-2xl border border-white/20 shadow-lg" style={{ backdropFilter: 'blur(20px)' }}>
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setSearchParams({ tab: tab.id }, { replace: true })}
                className="relative flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium flex-1 min-w-fit transition-all duration-200 z-10"
              >
                {isActive && (
                  <motion.div
                    layoutId="activeTabBg"
                    className="absolute inset-0 rounded-xl bg-gradient-to-br from-blue-500 via-blue-600 to-purple-600 shadow-xl"
                    style={{ boxShadow: '0 8px 32px rgba(59, 130, 246, 0.4)' }}
                    transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  />
                )}
                <Icon className={`w-4 h-4 relative z-10 transition-all duration-200 ${isActive ? 'text-white scale-110' : 'text-gray-600'}`} />
                <span className={`relative z-10 hidden sm:inline transition-all duration-200 ${isActive ? 'text-white font-semibold' : 'text-gray-600'}`}>
                  {tab.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-6">
        {activeTab === 'profile' && <ProfileTab />}
        {activeTab === 'notifications' && <NotificationsTab />}
        {activeTab === 'security' && <SecurityTab />}
        {activeTab === 'subscription' && <SubscriptionTab />}
        {activeTab === 'preferences' && <PreferencesTab />}
      </div>
    </div>
  );
}

// ── Profile ──────────────────────────────────────────────────────────────────

function timezones(current: string | null | undefined) {
  const intl = Intl as typeof Intl & { supportedValuesOf?: (key: string) => string[] };
  const list = intl.supportedValuesOf?.('timeZone') ?? ['UTC', 'Europe/Kyiv', 'Europe/Warsaw', 'Europe/Berlin', 'Europe/London', 'America/New_York'];
  return current && !list.includes(current) ? [current, ...list] : list;
}

function ProfileTab() {
  const { t } = useLanguage();
  const { user, setUser, logout } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState(user?.username ?? '');
  const [email, setEmail] = useState(user?.email ?? '');
  const [timezone, setTimezone] = useState(user?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [avatarUrl, setAvatarUrl] = useState(user?.avatar_url ?? '');
  const [avatarOpen, setAvatarOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteText, setDeleteText] = useState('');
  const zones = useMemo(() => timezones(user?.timezone), [user?.timezone]);

  const reset = () => {
    setUsername(user?.username ?? '');
    setEmail(user?.email ?? '');
    setTimezone(user?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone);
    setAvatarUrl(user?.avatar_url ?? '');
  };

  const handleSave = async () => {
    if (!user) return;
    setSaving(true);
    try {
      let updated = await settingsApi.updateProfile({
        username: username.trim(),
        timezone,
        avatar_url: avatarUrl.trim() || null,
      });
      const newEmail = email.trim().toLowerCase();
      if (newEmail !== user.email) {
        updated = await settingsApi.changeEmail(newEmail);
        toast.success(t.settings.profile.emailChanged);
      }
      // /settings/* returns a profile without capital/role — merge into the user
      setUser({ ...user, ...updated });
      toast.success(t.settings.profile.saved);
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteAccount = async () => {
    try {
      await usersApi.deleteMe();
      await logout();
      toast.success(t.settings.profile.accountDeleted);
      navigate('/login');
    } catch (err) {
      toast.error(errorMessage(err, t));
    }
  };

  return (
    <>
      <Card className="border-0 shadow-sm">
        <CardHeader>
          <CardTitle>{t.settings.profile.title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex items-center gap-6">
            <Avatar className="w-24 h-24">
              {avatarUrl && <AvatarImage src={avatarUrl} alt={username} />}
              <AvatarFallback className="text-2xl">{username ? username.slice(0, 2).toUpperCase() : <User className="w-12 h-12" />}</AvatarFallback>
            </Avatar>
            <div>
              <Button variant="outline" size="sm" onClick={() => setAvatarOpen(true)}>
                {t.settings.profile.changeAvatar}
              </Button>
              <p className="text-sm text-gray-500 mt-2">{t.settings.profile.avatarHint}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="username">{t.settings.profile.username}</Label>
              <Input id="username" value={username} minLength={3} maxLength={64} onChange={(e) => setUsername(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">{t.settings.profile.email}</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>{t.settings.profile.timezone}</Label>
              <Select value={timezone} onValueChange={setTimezone}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-72">
                  {zones.map((z) => (
                    <SelectItem key={z} value={z}>
                      {z}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="phone" className="flex items-center gap-2">
                {t.settings.profile.phone} <ComingSoonBadge />
              </Label>
              <Input id="phone" type="tel" placeholder={t.settings.profile.phonePlaceholder} disabled title={t.common.comingSoonHint} />
            </div>
          </div>

          <div className="flex gap-3">
            <Button onClick={handleSave} disabled={saving || username.trim().length < 3}>
              {saving ? t.common.saving : t.settings.profile.saveChanges}
            </Button>
            <Button variant="outline" onClick={reset} disabled={saving}>
              {t.settings.profile.cancel}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="border border-red-100 shadow-sm">
        <CardHeader>
          <CardTitle className="text-red-600">{t.settings.profile.dangerZone}</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-4 flex-wrap">
          <p className="text-sm text-gray-600">{t.settings.profile.deleteAccountDesc}</p>
          <Button
            variant="outline"
            className="text-red-600 border-red-200 hover:text-red-700"
            onClick={() => {
              setDeleteText('');
              setDeleteOpen(true);
            }}
          >
            {t.settings.profile.deleteAccount}
          </Button>
        </CardContent>
      </Card>

      <Dialog open={avatarOpen} onOpenChange={setAvatarOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t.settings.profile.changeAvatar}</DialogTitle>
            <DialogDescription>{t.settings.profile.avatarHint}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="avatar-url">{t.settings.profile.avatarUrl}</Label>
              <Input id="avatar-url" type="url" maxLength={512} placeholder="https://..." value={avatarUrl} onChange={(e) => setAvatarUrl(e.target.value)} />
            </div>
            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setAvatarUrl('')}>
                {t.settings.profile.removeAvatar}
              </Button>
              <Button className="flex-1" onClick={() => setAvatarOpen(false)}>
                {t.common.confirm}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t.settings.profile.deleteAccount}
        description={
          <span className="block space-y-3">
            <span className="block">{t.settings.profile.deleteAccountDesc}</span>
            <span className="block text-gray-900">{t.settings.profile.deleteAccountConfirm}</span>
            <Input value={deleteText} onChange={(e) => setDeleteText(e.target.value)} placeholder="DELETE" />
          </span>
        }
        confirmLabel={t.settings.profile.deleteAccount}
        confirmDisabled={deleteText !== 'DELETE'}
        onConfirm={handleDeleteAccount}
      />
    </>
  );
}

// ── Notifications ────────────────────────────────────────────────────────────

function NotificationsTab() {
  const { t } = useLanguage();
  const prefs = useApi(() => settingsApi.notifications(), []);

  const rows: { key: keyof NotificationPreferences; title: string; desc: string }[] = [
    { key: 'email_enabled', title: t.settings.notifications.email, desc: t.settings.notifications.emailDesc },
    { key: 'push_enabled', title: t.settings.notifications.push, desc: t.settings.notifications.pushDesc },
    { key: 'budget_limit_alerts', title: t.settings.notifications.budgetAlerts, desc: t.settings.notifications.budgetAlertsDesc },
    { key: 'recurring_reminders', title: t.settings.notifications.recurringReminders, desc: t.settings.notifications.recurringRemindersDesc },
    { key: 'goal_milestone_alerts', title: t.settings.notifications.goalMilestones, desc: t.settings.notifications.goalMilestonesDesc },
    { key: 'monthly_summary', title: t.settings.notifications.monthlyReports, desc: t.settings.notifications.monthlyReportsDesc },
  ];

  const toggle = async (key: keyof NotificationPreferences, value: boolean) => {
    if (!prefs.data) return;
    const previous = prefs.data;
    prefs.setData({ ...previous, [key]: value }); // optimistic
    try {
      prefs.setData(await settingsApi.updateNotifications({ [key]: value }));
      toast.success(t.settings.notifications.saved);
      notifyDataChanged(); // alerts in the top bar depend on these
    } catch (err) {
      prefs.setData(previous);
      toast.error(errorMessage(err, t));
    }
  };

  return (
    <Card className="border-0 shadow-sm">
      <CardHeader>
        <CardTitle>{t.settings.notifications.title}</CardTitle>
        <p className="text-xs text-gray-500">{t.settings.notifications.deliveryHint}</p>
      </CardHeader>
      <CardContent>
        <AsyncBlock state={prefs}>
          {(data) => (
            <div className="space-y-2">
              {rows.map((row, i) => (
                <div key={row.key} className={`flex items-center justify-between py-3 ${i < rows.length - 1 ? 'border-b border-gray-100' : ''}`}>
                  <div>
                    <h4 className="font-medium text-gray-900">{row.title}</h4>
                    <p className="text-sm text-gray-500 mt-1">{row.desc}</p>
                  </div>
                  <Switch checked={data[row.key]} onCheckedChange={(v) => toggle(row.key, v)} />
                </div>
              ))}
            </div>
          )}
        </AsyncBlock>
      </CardContent>
    </Card>
  );
}

// ── Security ─────────────────────────────────────────────────────────────────

function SecurityTab() {
  const { t } = useLanguage();
  const { user, refreshUser } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [savingPassword, setSavingPassword] = useState(false);

  const [setup, setSetup] = useState<TwoFASetup | null>(null);
  const [disableOpen, setDisableOpen] = useState(false);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);

  const handlePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!current || !next || !confirm) {
      toast.error(t.settings.security.fillAllFields);
      return;
    }
    if (next !== confirm) {
      toast.error(t.settings.security.passwordsDoNotMatch);
      return;
    }
    setSavingPassword(true);
    try {
      await authApi.changePassword(current, next);
      toast.success(t.settings.security.passwordUpdated);
      setCurrent('');
      setNext('');
      setConfirm('');
      notifyDataChanged();   // password health card
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setSavingPassword(false);
    }
  };

  const startSetup = async () => {
    setBusy(true);
    try {
      setCode('');
      setSetup(await twoFaApi.setup());
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  const confirm2fa = async (mode: 'enable' | 'disable', value = code) => {
    if (value.length !== 6) return;
    setBusy(true);
    try {
      if (mode === 'enable') await twoFaApi.verify(value);
      else await twoFaApi.disable(value);
      toast.success(mode === 'enable' ? t.settings.security.enabledSuccess : t.settings.security.disabledSuccess);
      setSetup(null);
      setDisableOpen(false);
      await refreshUser();
    } catch (err) {
      toast.error(errorMessage(err, t));
      setCode('');
      setAttempt((n) => n + 1);
    } finally {
      setBusy(false);
    }
  };

  const enabled = Boolean(user?.twofa_enabled);
  const otp = (mode: 'enable' | 'disable') => (
    <div className="flex flex-col items-center gap-3">
      <InputOTP key={attempt} maxLength={6} value={code} onChange={setCode} onComplete={(v: string) => void confirm2fa(mode, v)} disabled={busy} autoFocus>
        <InputOTPGroup>
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <InputOTPSlot key={i} index={i} />
          ))}
        </InputOTPGroup>
      </InputOTP>
      <Button className="w-full" variant={mode === 'disable' ? 'destructive' : 'default'} disabled={busy || code.length !== 6} onClick={() => confirm2fa(mode)}>
        {mode === 'enable' ? t.settings.security.confirmEnable : t.settings.security.confirmDisable}
      </Button>
    </div>
  );

  return (
    <div className="space-y-6">
      <PasswordHealthCard />

      <Card className="border-0 shadow-sm">
        <CardHeader>
          <CardTitle>{t.settings.security.password}</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handlePassword}>
            <div className="space-y-2">
              <Label htmlFor="current-password">{t.settings.security.currentPassword}</Label>
              <Input id="current-password" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-password">{t.settings.security.newPassword}</Label>
              <Input id="new-password" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
              <PasswordStrengthMeter password={next} username={user?.username} email={user?.email} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm-password">{t.settings.security.confirmPassword}</Label>
              <Input id="confirm-password" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </div>
            <Button type="submit" disabled={savingPassword}>
              {savingPassword ? t.common.saving : t.settings.security.updatePassword}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card className="border-0 shadow-sm">
        <CardHeader>
          <CardTitle>{t.settings.security.twoFactor}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="font-medium text-gray-900">{t.settings.security.twoFactorStatus}</h4>
              <p className="text-sm text-gray-500 mt-1">{enabled ? t.settings.security.twoFactorEnabled : t.settings.security.twoFactorDisabled}</p>
            </div>
            <Badge variant={enabled ? 'default' : 'secondary'}>{enabled ? t.settings.security.enabled : t.settings.security.disabled}</Badge>
          </div>
          <Button
            variant={enabled ? 'destructive' : 'default'}
            disabled={busy}
            onClick={() => {
              if (enabled) {
                setCode('');
                setDisableOpen(true);
              } else void startSetup();
            }}
          >
            <ShieldCheck className="w-4 h-4 mr-2" />
            {enabled ? t.settings.security.disable2FA : t.settings.security.enable2FA}
          </Button>
        </CardContent>
      </Card>

      <PasskeysCard />

      <ActivityCard />

      {/* Enable 2FA: scan QR, confirm with a code */}
      <Dialog open={Boolean(setup)} onOpenChange={(open) => !open && setSetup(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t.settings.security.enable2FA}</DialogTitle>
            <DialogDescription>{t.settings.security.scanQr}</DialogDescription>
          </DialogHeader>
          {setup && (
            <div className="space-y-4">
              <img src={`data:image/png;base64,${setup.qr_code_base64}`} alt="2FA QR" className="w-48 h-48 mx-auto" />
              <div className="text-center">
                <p className="text-xs text-gray-500">{t.settings.security.secretKey}</p>
                <code className="text-sm font-mono bg-gray-100 rounded px-2 py-1 select-all">{setup.secret}</code>
              </div>
              <p className="text-sm text-center text-gray-700">{t.settings.security.enterCode}</p>
              {otp('enable')}
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={disableOpen} onOpenChange={setDisableOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t.settings.security.disable2FA}</DialogTitle>
            <DialogDescription>{t.settings.security.enterCode}</DialogDescription>
          </DialogHeader>
          {otp('disable')}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Subscription ─────────────────────────────────────────────────────────────

function SubscriptionTab() {
  const { t } = useLanguage();
  const { refreshUser } = useAuth();
  const subscription = useApi(() => settingsApi.subscription(), []);
  const [busy, setBusy] = useState(false);
  const [downgradeOpen, setDowngradeOpen] = useState(false);

  const change = async (to: 'PRO' | 'FREE') => {
    setBusy(true);
    try {
      if (to === 'PRO') await settingsApi.upgrade();
      else await settingsApi.downgrade();
      toast.success(to === 'PRO' ? t.settings.subscription.upgraded : t.settings.subscription.downgraded);
      subscription.reload();
      await refreshUser();
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AsyncBlock state={subscription}>
      {(data) => {
        const isPro = data.plan === 'PRO';
        return (
          <div className="space-y-6">
            <Card className="border-0 shadow-sm bg-gradient-to-br from-blue-50 to-purple-50">
              <CardContent className="pt-6">
                <div className="flex items-center justify-between flex-wrap gap-4">
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{t.settings.subscription.currentPlan}</p>
                    <Badge className={isPro ? 'bg-gradient-to-r from-blue-600 to-purple-600 mb-2' : 'mb-2'} variant={isPro ? 'default' : 'secondary'}>
                      {data.plan}
                    </Badge>
                    <h3 className="text-2xl font-semibold text-gray-900">{isPro ? t.settings.subscription.pro : t.settings.subscription.free}</h3>
                    <p className="text-sm text-gray-600 mt-1">{isPro ? t.settings.subscription.proDesc : t.settings.subscription.freeDesc}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-3xl font-semibold text-gray-900">{isPro ? t.settings.subscription.price : '$0'}</p>
                    <p className="text-sm text-gray-600 mt-1">{t.settings.subscription.perMonth}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-sm">
              <CardHeader>
                <CardTitle>{t.settings.subscription.features}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {data.features.map((feature) => (
                    <div key={feature.label} className="flex items-center gap-3">
                      <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${feature.available ? 'bg-green-500' : 'bg-gray-200'}`}>
                        {feature.available ? <Check className="w-3 h-3 text-white" /> : <X className="w-3 h-3 text-gray-500" />}
                      </div>
                      <span className={feature.available ? 'text-gray-700' : 'text-gray-400'}>
                        {t.settings.subscription.featureLabels[feature.label] ?? feature.label}
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-sm">
              <CardHeader>
                <CardTitle>{t.settings.subscription.manage}</CardTitle>
                <p className="text-xs text-gray-500">{t.settings.subscription.paymentsHint}</p>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <Button variant="outline" className="w-full" disabled title={t.common.comingSoonHint}>
                    {t.settings.subscription.updatePayment} <ComingSoonBadge />
                  </Button>
                  <Button variant="outline" className="w-full" disabled title={t.common.comingSoonHint}>
                    {t.settings.subscription.viewBilling} <ComingSoonBadge />
                  </Button>
                  {isPro ? (
                    <Button
                      variant="outline"
                      className="w-full text-red-600 hover:text-red-700 border-red-200 hover:border-red-300"
                      disabled={busy}
                      onClick={() => setDowngradeOpen(true)}
                    >
                      {t.settings.subscription.downgrade}
                    </Button>
                  ) : (
                    <Button className="w-full" disabled={busy} onClick={() => change('PRO')}>
                      {t.settings.subscription.upgrade}
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>

            <ConfirmDialog
              open={downgradeOpen}
              onOpenChange={setDowngradeOpen}
              title={t.settings.subscription.downgrade}
              description={t.settings.subscription.downgradeConfirm}
              confirmLabel={t.common.confirm}
              onConfirm={() => change('FREE')}
            />
          </div>
        );
      }}
    </AsyncBlock>
  );
}

// ── Preferences ──────────────────────────────────────────────────────────────

function PreferencesTab() {
  const { t, language, setLanguage, dateFormat, setDateFormat, formatDate } = useLanguage();
  const { user, refreshUser } = useAuth();
  const [currency, setCurrency] = useState<string>(user?.default_currency ?? 'USD');

  useEffect(() => {
    if (user) setCurrency(user.default_currency);
  }, [user]);

  const changeCurrency = async (value: string) => {
    const previous = currency;
    setCurrency(value);
    try {
      await settingsApi.updateCurrency(value);
      await refreshUser();
      notifyDataChanged(); // analytics are reported in the default currency
      toast.success(t.settings.preferences.currencySaved);
    } catch (err) {
      setCurrency(previous);
      toast.error(errorMessage(err, t));
    }
  };

  return (
    <Card className="border-0 shadow-sm">
      <CardHeader>
        <CardTitle>{t.settings.preferences.title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-2">
          <Label>{t.settings.preferences.currency}</Label>
          <Select value={currency} onValueChange={changeCurrency}>
            <SelectTrigger>
              <Globe className="w-4 h-4 mr-2" />
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
          <p className="text-xs text-gray-500">{t.settings.preferences.currencyHint}</p>
        </div>

        <div className="space-y-2">
          <Label>{t.settings.preferences.language}</Label>
          <Select value={language} onValueChange={(value) => setLanguage(value as Language)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="uk">🇺🇦 Українська</SelectItem>
              <SelectItem value="en">🇺🇸 English</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>{t.settings.preferences.dateFormat}</Label>
          <Select
            value={dateFormat}
            onValueChange={(value) => {
              setDateFormat(value as DateFormat);
              toast.success(t.settings.preferences.dateFormatSaved);
            }}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DATE_FORMATS.map((f) => (
                <SelectItem key={f} value={f}>
                  {f}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-gray-500">{formatDate(new Date())}</p>
        </div>

        <div className="space-y-2">
          <Label className="flex items-center gap-2">
            {t.settings.preferences.theme} <ComingSoonBadge />
          </Label>
          <Select value="light" disabled>
            <SelectTrigger title={t.common.comingSoonHint}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="light">{t.settings.preferences.themeOptions.light}</SelectItem>
              <SelectItem value="dark">{t.settings.preferences.themeOptions.dark}</SelectItem>
              <SelectItem value="auto">{t.settings.preferences.themeOptions.auto}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center justify-between py-3 border-t border-gray-100">
          <div>
            <h4 className="font-medium text-gray-900 flex items-center gap-2">
              {t.settings.preferences.soundEffects} <ComingSoonBadge />
            </h4>
            <p className="text-sm text-gray-500 mt-1">{t.settings.preferences.soundEffectsDesc}</p>
          </div>
          <Switch disabled />
        </div>
      </CardContent>
    </Card>
  );
}
