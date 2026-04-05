import { useState } from 'react';
import { Bell, ChevronDown, User, LogOut } from 'lucide-react';
import { useNavigate } from 'react-router';
import { mockBudgets, mockNotifications, mockUser } from '../../data/mockData';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';
import { Badge } from '../ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '../ui/avatar';
import { useAuth } from '../../context/AuthContext';
import { toast } from 'sonner';
import { useLanguage } from '../../i18n/LanguageContext';

export function TopBar() {
  const { t } = useLanguage();
  const [selectedBudget, setSelectedBudget] = useState(mockBudgets[0]);
  const unreadCount = mockNotifications.filter((n) => !n.read).length;
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    toast.success(t.header.loggedOutSuccess);
    navigate('/login');
  };

  return (
    <div className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6">
      {/* Budget Switcher */}
      <DropdownMenu>
        <DropdownMenuTrigger className="flex items-center gap-2 px-4 py-2 rounded-lg hover:bg-gray-50 transition-colors">
          <Wallet className="w-5 h-5 text-gray-600" />
          <div className="flex flex-col items-start">
            <span className="text-sm font-medium text-gray-900">
              {t.mockData[selectedBudget.name as keyof typeof t.mockData]}
            </span>
            <span className="text-xs text-gray-500">
              {selectedBudget.currency} {selectedBudget.balance.toLocaleString()}
            </span>
          </div>
          <ChevronDown className="w-4 h-4 text-gray-400" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-64">
          {mockBudgets.map((budget) => (
            <DropdownMenuItem
              key={budget.id}
              onClick={() => setSelectedBudget(budget)}
              className="flex items-start gap-3 p-3"
            >
              <div className="flex-1">
                <div className="font-medium text-sm">{t.mockData[budget.name as keyof typeof t.mockData]}</div>
                <div className="text-xs text-gray-500 mt-0.5">
                  {budget.type === 'personal' ? t.budgets.personal : budget.type === 'family' ? t.budgets.family : t.budgets.business} •{' '}
                  {budget.currency} {budget.balance.toLocaleString()}
                </div>
              </div>
              {selectedBudget.id === budget.id && (
                <div className="w-2 h-2 bg-blue-600 rounded-full mt-1.5" />
              )}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem className="text-blue-600">
            + {t.header.createNewBudget}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Right Side */}
      <div className="flex items-center gap-4">
        {/* Notifications */}
        <DropdownMenu>
          <DropdownMenuTrigger className="relative p-2 rounded-lg hover:bg-gray-100 transition-colors">
            <Bell className="w-5 h-5 text-gray-600" />
            {unreadCount > 0 && (
              <Badge className="absolute -top-1 -right-1 h-5 w-5 flex items-center justify-center p-0 bg-red-500 text-white text-xs">
                {unreadCount}
              </Badge>
            )}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80">
            <div className="px-3 py-2 border-b">
              <div className="font-medium text-sm">{t.header.notifications}</div>
            </div>
            {mockNotifications.slice(0, 4).map((notification) => (
              <DropdownMenuItem key={notification.id} className="flex flex-col items-start gap-1 p-3">
                <div className="flex items-center gap-2 w-full">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      notification.type === 'warning'
                        ? 'bg-orange-500'
                        : notification.type === 'success'
                        ? 'bg-green-500'
                        : 'bg-blue-500'
                    }`}
                  />
                  <div className="font-medium text-sm flex-1">{t.mockData[notification.title as keyof typeof t.mockData]}</div>
                  {!notification.read && (
                    <div className="w-2 h-2 bg-blue-600 rounded-full" />
                  )}
                </div>
                <div className="text-xs text-gray-600 ml-4">{t.mockData[notification.message as keyof typeof t.mockData]}</div>
                <div className="text-xs text-gray-400 ml-4">{notification.date}</div>
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-blue-600 text-center justify-center">
              {t.header.viewAllNotifications}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Profile */}
        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center gap-3 pl-3 pr-2 py-1.5 rounded-lg hover:bg-gray-100 transition-colors">
            <div className="flex flex-col items-end">
              <span className="text-sm font-medium text-gray-900">{mockUser.name}</span>
              <span className="text-xs text-gray-500">{mockUser.subscription.toUpperCase()}</span>
            </div>
            <Avatar className="w-9 h-9">
              <AvatarImage src={mockUser.avatar} alt={mockUser.name} />
              <AvatarFallback>
                <User className="w-5 h-5" />
              </AvatarFallback>
            </Avatar>
            <ChevronDown className="w-4 h-4 text-gray-400" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuItem onClick={() => navigate('/settings')}>
              {t.header.profileSettings}
            </DropdownMenuItem>
            <DropdownMenuItem>{t.header.subscription}</DropdownMenuItem>
            <DropdownMenuItem>{t.header.security}</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleLogout} className="text-red-600">
              <LogOut className="w-4 h-4 mr-2" />
              {t.header.logOut}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}

function Wallet(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...props}
    >
      <path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1" />
      <path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4" />
    </svg>
  );
}