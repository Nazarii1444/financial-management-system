import { useState, useRef, useEffect } from 'react';
import { User, Bell, Lock, CreditCard, Palette, Globe } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Switch } from '../components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { Avatar, AvatarFallback, AvatarImage } from '../components/ui/avatar';
import { Badge } from '../components/ui/badge';
import { mockUser } from '../data/mockData';
import { useLanguage } from '../i18n/LanguageContext';
import { motion } from 'motion/react';

export function Settings() {
  const { t, language, setLanguage } = useLanguage();
  const [twoFactorEnabled, setTwoFactorEnabled] = useState(mockUser.twoFactorEnabled);
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [pushNotifications, setPushNotifications] = useState(true);
  const [budgetAlerts, setBudgetAlerts] = useState(true);
  const [activeTab, setActiveTab] = useState('profile');

  const tabs = [
    { id: 'profile', label: t.settings.tabs.profile, icon: User },
    { id: 'notifications', label: t.settings.tabs.notifications, icon: Bell },
    { id: 'security', label: t.settings.tabs.security, icon: Lock },
    { id: 'subscription', label: t.settings.tabs.subscription, icon: CreditCard },
    { id: 'preferences', label: t.settings.tabs.preferences, icon: Palette },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">{t.settings.title}</h1>
        <p className="text-sm text-gray-500 mt-1">
          {t.settings.subtitle}
        </p>
      </div>

      {/* Liquid Glass Tab Selector */}
      <div className="relative">
        <div className="relative flex gap-2 p-2 bg-gradient-to-br from-white/90 via-gray-50/80 to-gray-100/90 rounded-2xl border border-white/20 shadow-lg" style={{ backdropFilter: 'blur(20px)' }}>
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className="relative flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium flex-1 min-w-fit transition-all duration-200 z-10"
              >
                {isActive && (
                  <motion.div
                    layoutId="activeTabBg"
                    className="absolute inset-0 rounded-xl bg-gradient-to-br from-blue-500 via-blue-600 to-purple-600 shadow-xl"
                    style={{
                      boxShadow: '0 8px 32px rgba(59, 130, 246, 0.4)',
                    }}
                    transition={{
                      type: 'spring',
                      stiffness: 400,
                      damping: 30,
                    }}
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
        {/* Profile Tab */}
        {activeTab === 'profile' && (
          <Card className="border-0 shadow-sm">
            <CardHeader>
              <CardTitle>{t.settings.profile.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center gap-6">
                <Avatar className="w-24 h-24">
                  <AvatarImage src={mockUser.avatar} alt={mockUser.name} />
                  <AvatarFallback>
                    <User className="w-12 h-12" />
                  </AvatarFallback>
                </Avatar>
                <div>
                  <Button variant="outline" size="sm">
                    {t.settings.profile.changeAvatar}
                  </Button>
                  <p className="text-sm text-gray-500 mt-2">
                    {t.settings.profile.avatarHint}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="name">{t.settings.profile.fullName}</Label>
                  <Input id="name" defaultValue={mockUser.name} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email">{t.settings.profile.email}</Label>
                  <Input id="email" type="email" defaultValue={mockUser.email} />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="phone">{t.settings.profile.phone}</Label>
                <Input id="phone" type="tel" placeholder={t.settings.profile.phonePlaceholder} />
              </div>

              <div className="flex gap-3">
                <Button>{t.settings.profile.saveChanges}</Button>
                <Button variant="outline">{t.settings.profile.cancel}</Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Notifications Tab */}
        {activeTab === 'notifications' && (
          <Card className="border-0 shadow-sm">
            <CardHeader>
              <CardTitle>{t.settings.notifications.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between py-3 border-b border-gray-100">
                <div>
                  <h4 className="font-medium text-gray-900">{t.settings.notifications.email}</h4>
                  <p className="text-sm text-gray-500 mt-1">
                    {t.settings.notifications.emailDesc}
                  </p>
                </div>
                <Switch
                  checked={emailNotifications}
                  onCheckedChange={setEmailNotifications}
                />
              </div>

              <div className="flex items-center justify-between py-3 border-b border-gray-100">
                <div>
                  <h4 className="font-medium text-gray-900">{t.settings.notifications.push}</h4>
                  <p className="text-sm text-gray-500 mt-1">
                    {t.settings.notifications.pushDesc}
                  </p>
                </div>
                <Switch
                  checked={pushNotifications}
                  onCheckedChange={setPushNotifications}
                />
              </div>

              <div className="flex items-center justify-between py-3 border-b border-gray-100">
                <div>
                  <h4 className="font-medium text-gray-900">{t.settings.notifications.budgetAlerts}</h4>
                  <p className="text-sm text-gray-500 mt-1">
                    {t.settings.notifications.budgetAlertsDesc}
                  </p>
                </div>
                <Switch checked={budgetAlerts} onCheckedChange={setBudgetAlerts} />
              </div>

              <div className="flex items-center justify-between py-3 border-b border-gray-100">
                <div>
                  <h4 className="font-medium text-gray-900">{t.settings.notifications.transactionUpdates}</h4>
                  <p className="text-sm text-gray-500 mt-1">
                    {t.settings.notifications.transactionUpdatesDesc}
                  </p>
                </div>
                <Switch defaultChecked />
              </div>

              <div className="flex items-center justify-between py-3 border-b border-gray-100">
                <div>
                  <h4 className="font-medium text-gray-900">{t.settings.notifications.monthlyReports}</h4>
                  <p className="text-sm text-gray-500 mt-1">
                    {t.settings.notifications.monthlyReportsDesc}
                  </p>
                </div>
                <Switch defaultChecked />
              </div>

              <div className="flex items-center justify-between py-3">
                <div>
                  <h4 className="font-medium text-gray-900">{t.settings.notifications.marketing}</h4>
                  <p className="text-sm text-gray-500 mt-1">
                    {t.settings.notifications.marketingDesc}
                  </p>
                </div>
                <Switch />
              </div>
            </CardContent>
          </Card>
        )}

        {/* Security Tab */}
        {activeTab === 'security' && (
          <div className="space-y-6">
            <Card className="border-0 shadow-sm">
              <CardHeader>
                <CardTitle>{t.settings.security.password}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="current-password">{t.settings.security.currentPassword}</Label>
                  <Input id="current-password" type="password" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="new-password">{t.settings.security.newPassword}</Label>
                  <Input id="new-password" type="password" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirm-password">{t.settings.security.confirmPassword}</Label>
                  <Input id="confirm-password" type="password" />
                </div>
                <Button>{t.settings.security.updatePassword}</Button>
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
                    <p className="text-sm text-gray-500 mt-1">
                      {twoFactorEnabled
                        ? t.settings.security.twoFactorEnabled
                        : t.settings.security.twoFactorDisabled}
                    </p>
                  </div>
                  <Badge variant={twoFactorEnabled ? 'default' : 'secondary'}>
                    {twoFactorEnabled ? t.settings.security.enabled : t.settings.security.disabled}
                  </Badge>
                </div>
                <Button
                  variant={twoFactorEnabled ? 'destructive' : 'default'}
                  onClick={() => setTwoFactorEnabled(!twoFactorEnabled)}
                >
                  {twoFactorEnabled ? t.settings.security.disable2FA : t.settings.security.enable2FA}
                </Button>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-sm">
              <CardHeader>
                <CardTitle>{t.settings.security.activeSessions}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between p-3 rounded-lg bg-gray-50">
                  <div>
                    <h4 className="font-medium text-gray-900">{t.settings.security.currentSession}</h4>
                    <p className="text-sm text-gray-500 mt-1">
                      Chrome on macOS • San Francisco, CA
                    </p>
                  </div>
                  <Badge>{t.settings.security.active}</Badge>
                </div>
                <div className="flex items-center justify-between p-3 rounded-lg border border-gray-100">
                  <div>
                    <h4 className="font-medium text-gray-900">iPhone 14 Pro</h4>
                    <p className="text-sm text-gray-500 mt-1">
                      Safari on iOS • Last active 2 hours ago
                    </p>
                  </div>
                  <Button variant="ghost" size="sm">
                    {t.settings.security.revoke}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Subscription Tab */}
        {activeTab === 'subscription' && (
          <div className="space-y-6">
            <Card className="border-0 shadow-sm bg-gradient-to-br from-blue-50 to-purple-50">
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div>
                    <Badge className="bg-gradient-to-r from-blue-600 to-purple-600 mb-2">
                      {mockUser.subscription.toUpperCase()}
                    </Badge>
                    <h3 className="text-2xl font-semibold text-gray-900">
                      {t.settings.subscription.plan}
                    </h3>
                    <p className="text-sm text-gray-600 mt-1">
                      {t.settings.subscription.billingInfo}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-3xl font-semibold text-gray-900">$9.99</p>
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
                <div className="space-y-3">
                  {[
                    t.settings.subscription.featuresList.unlimitedBudgets,
                    t.settings.subscription.featuresList.aiInsights,
                    t.settings.subscription.featuresList.advancedReporting,
                    t.settings.subscription.featuresList.multiCurrency,
                    t.settings.subscription.featuresList.prioritySupport,
                    t.settings.subscription.featuresList.exportData,
                    t.settings.subscription.featuresList.ocrScanning,
                    t.settings.subscription.featuresList.collaborative,
                  ].map((feature) => (
                    <div key={feature} className="flex items-center gap-3">
                      <div className="w-5 h-5 bg-green-500 rounded-full flex items-center justify-center flex-shrink-0">
                        <svg
                          className="w-3 h-3 text-white"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={3}
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                      </div>
                      <span className="text-gray-700">{feature}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-sm">
              <CardHeader>
                <CardTitle>{t.settings.subscription.manage}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <Button variant="outline" className="w-full">
                    {t.settings.subscription.updatePayment}
                  </Button>
                  <Button variant="outline" className="w-full">
                    {t.settings.subscription.viewBilling}
                  </Button>
                  <Button variant="outline" className="w-full text-red-600 hover:text-red-700 border-red-200 hover:border-red-300">
                    {t.settings.subscription.cancel}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Preferences Tab */}
        {activeTab === 'preferences' && (
          <Card className="border-0 shadow-sm">
            <CardHeader>
              <CardTitle>{t.settings.preferences.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="currency">{t.settings.preferences.currency}</Label>
                <Select defaultValue={mockUser.defaultCurrency}>
                  <SelectTrigger>
                    <Globe className="w-4 h-4 mr-2" />
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="USD">USD ($) - US Dollar</SelectItem>
                    <SelectItem value="EUR">EUR (€) - Euro</SelectItem>
                    <SelectItem value="GBP">GBP (£) - British Pound</SelectItem>
                    <SelectItem value="JPY">JPY (¥) - Japanese Yen</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="language">{t.settings.preferences.language}</Label>
                <Select value={language} onValueChange={(value) => setLanguage(value as 'en' | 'uk')}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="en">🇺🇸 English</SelectItem>
                    <SelectItem value="uk">🇺🇦 Українська</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="theme">{t.settings.preferences.theme}</Label>
                <Select defaultValue="light">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="light">{t.settings.preferences.themeOptions.light}</SelectItem>
                    <SelectItem value="dark">{t.settings.preferences.themeOptions.dark}</SelectItem>
                    <SelectItem value="auto">{t.settings.preferences.themeOptions.auto}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="dateFormat">{t.settings.preferences.dateFormat}</Label>
                <Select defaultValue="MM/DD/YYYY">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="MM/DD/YYYY">MM/DD/YYYY</SelectItem>
                    <SelectItem value="DD/MM/YYYY">DD/MM/YYYY</SelectItem>
                    <SelectItem value="YYYY-MM-DD">YYYY-MM-DD</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between py-3 border-t border-gray-100">
                <div>
                  <h4 className="font-medium text-gray-900">{t.settings.preferences.soundEffects}</h4>
                  <p className="text-sm text-gray-500 mt-1">
                    {t.settings.preferences.soundEffectsDesc}
                  </p>
                </div>
                <Switch defaultChecked />
              </div>

              <div className="flex gap-3 pt-4">
                <Button>{t.settings.preferences.save}</Button>
                <Button variant="outline">{t.settings.preferences.reset}</Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}