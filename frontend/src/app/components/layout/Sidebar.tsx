import { Link, useLocation } from 'react-router';
import {
  LayoutDashboard,
  Receipt,
  Wallet,
  Target,
  BarChart3,
  Settings,
  TrendingUp,
} from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { Crown } from 'lucide-react';
import { useLanguage } from '../../i18n/LanguageContext';
import { useAuth } from '../../context/AuthContext';
import { settingsApi } from '../../lib/api';
import { errorMessage } from '../../lib/errors';
import { motion } from 'motion/react';

export function Sidebar() {
  const location = useLocation();
  const { t } = useLanguage();
  const { user, refreshUser } = useAuth();
  const [upgrading, setUpgrading] = useState(false);

  const handleUpgrade = async () => {
    setUpgrading(true);
    try {
      await settingsApi.upgrade();
      await refreshUser();
      toast.success(t.common.upgradedSuccess);
    } catch (err) {
      toast.error(errorMessage(err, t));
    } finally {
      setUpgrading(false);
    }
  };

  const navigation = [
    { name: t.nav.dashboard, href: '/', icon: LayoutDashboard },
    { name: t.nav.transactions, href: '/transactions', icon: Receipt },
    { name: t.nav.budgets, href: '/budgets', icon: Wallet },
    { name: t.nav.goals, href: '/goals', icon: Target },
    { name: t.nav.reports, href: '/reports', icon: BarChart3 },
    { name: t.nav.settings, href: '/settings', icon: Settings },
  ];

  return (
    <div className="w-64 bg-white border-r border-gray-200 flex flex-col">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-gray-200">
        <TrendingUp className="w-8 h-8 text-blue-600" />
        <span className="ml-3 font-semibold text-xl text-gray-900">FinanceHub</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 relative">
        {navigation.map((item) => {
          const isActive = location.pathname === item.href;
          const Icon = item.icon;

          return (
            <Link
              key={item.name}
              to={item.href}
              className="relative flex items-center px-3 py-2.5 rounded-lg text-sm transition-colors z-10"
            >
              {isActive && (
                <motion.div
                  layoutId="sidebarActiveNav"
                  className="absolute inset-0 bg-gradient-to-r from-blue-50 to-blue-100 rounded-lg"
                  style={{
                    boxShadow: '0 2px 8px rgba(59, 130, 246, 0.15)',
                  }}
                  transition={{
                    type: 'spring',
                    stiffness: 400,
                    damping: 30,
                  }}
                />
              )}
              <Icon className={`w-5 h-5 mr-3 relative z-10 transition-all duration-200 ${isActive ? 'text-blue-600 scale-110' : 'text-gray-700'}`} />
              <span className={`relative z-10 transition-all duration-200 ${isActive ? 'text-blue-600 font-medium' : 'text-gray-700'}`}>
                {item.name}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* Upgrade Banner */}
      {user?.subscription_plan === 'PRO' ? (
        <div className="p-4 m-3 bg-gradient-to-br from-purple-50 to-blue-50 rounded-xl border border-blue-100">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-900">
            <Crown className="w-4 h-4 text-purple-600" />
            {t.common.youArePro}
          </div>
          <div className="text-xs text-gray-500 mt-1">{t.common.youAreProDesc}</div>
        </div>
      ) : (
        <div className="p-4 m-3 bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl text-white">
          <div className="text-sm font-medium mb-1">{t.common.upgradeToPro}</div>
          <div className="text-xs text-blue-100 mb-3">
            {t.common.upgradeProDesc}
          </div>
          <button
            onClick={handleUpgrade}
            disabled={upgrading}
            className="w-full bg-white text-blue-600 text-sm py-2 rounded-lg hover:bg-blue-50 transition-colors disabled:opacity-60"
          >
            {upgrading ? t.common.loading : t.common.upgradeNow}
          </button>
        </div>
      )}
    </div>
  );
}