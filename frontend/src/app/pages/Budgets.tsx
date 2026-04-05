import { useState } from 'react';
import { Plus, Users, TrendingUp, AlertCircle, UserPlus, Mail, MoreVertical, Trash2, Shield, Edit2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Progress } from '../components/ui/progress';
import { Badge } from '../components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogDescription,
} from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Input } from '../components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import { mockBudgets, categories, mockTransactions } from '../data/mockData';
import { BudgetType } from '../types';
import { useLanguage } from '../i18n/LanguageContext';
import { toast } from 'sonner';
import { Avatar, AvatarFallback, AvatarImage } from '../components/ui/avatar';

interface BudgetCategory {
  category: string;
  allocated: number;
  spent: number;
  color: string;
}

export function Budgets() {
  const { t, translateCategory } = useLanguage();
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [manageMembersDialogOpen, setManageMembersDialogOpen] = useState(false);
  const [addMemberDialogOpen, setAddMemberDialogOpen] = useState(false);
  const [selectedBudget, setSelectedBudget] = useState<typeof mockBudgets[0] | null>(null);
  
  // Calculate category budgets
  const categoryBudgets: BudgetCategory[] = [
    { category: 'Food & Dining', allocated: 500, spent: 438, color: '#f59e0b' },
    { category: 'Bills & Utilities', allocated: 1200, spent: 1200, color: '#f97316' },
    { category: 'Transportation', allocated: 300, spent: 245, color: '#ef4444' },
    { category: 'Shopping', allocated: 400, spent: 330, color: '#ec4899' },
    { category: 'Entertainment', allocated: 200, spent: 156, color: '#a855f7' },
    { category: 'Healthcare', allocated: 150, spent: 120, color: '#06b6d4' },
  ];

  const totalAllocated = categoryBudgets.reduce((sum, b) => sum + b.allocated, 0);
  const totalSpent = categoryBudgets.reduce((sum, b) => sum + b.spent, 0);
  const overallProgress = (totalSpent / totalAllocated) * 100;

  const handleCreateBudget = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setIsCreateDialogOpen(false);
    toast.success(t.budgets.budgetCreatedSuccess);
  };

  const handleAddMember = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    const email = formData.get('email');
    toast.success(t.budgets.memberAddedSuccess.replace('{email}', email as string));
    setAddMemberDialogOpen(false);
  };

  const handleRemoveMember = (memberName: string) => {
    toast.success(t.budgets.memberRemovedSuccess.replace('{name}', memberName));
  };

  const handleChangeRole = (memberName: string, newRole: string) => {
    const roleText = newRole === 'editor' ? t.budgets.editor : t.budgets.viewer;
    toast.success(t.budgets.roleChangedSuccess.replace('{name}', memberName).replace('{role}', roleText));
  };

  const openManageMembers = (budget: typeof mockBudgets[0]) => {
    setSelectedBudget(budget);
    setManageMembersDialogOpen(true);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">{t.budgets.budgetPlanning}</h1>
          <p className="text-sm text-gray-500 mt-1">
            {t.budgets.planTrackLimits}
          </p>
        </div>
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button size="sm">
              <Plus className="w-4 h-4 mr-2" />
              {t.budgets.createBudget}
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>{t.budgets.createNewBudget}</DialogTitle>
              <DialogDescription>
                {t.budgets.createNewBudgetDescription}
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleCreateBudget} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">{t.budgets.budgetName}</Label>
                <Input
                  id="name"
                  name="name"
                  placeholder={t.budgets.budgetNamePlaceholder}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="type">{t.budgets.type}</Label>
                <Select name="type" defaultValue="personal" required>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="personal">{t.budgets.personal}</SelectItem>
                    <SelectItem value="family">{t.budgets.family}</SelectItem>
                    <SelectItem value="business">{t.budgets.business}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="currency">{t.budgets.currency}</Label>
                <Select name="currency" defaultValue="USD" required>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="USD">USD ($)</SelectItem>
                    <SelectItem value="EUR">EUR (€)</SelectItem>
                    <SelectItem value="GBP">GBP (£)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex gap-3 pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsCreateDialogOpen(false)}
                  className="flex-1"
                >
                  {t.common.cancel}
                </Button>
                <Button type="submit" className="flex-1">
                  {t.budgets.create}
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Current Budgets */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {mockBudgets.map((budget) => (
          <Card 
            key={budget.id} 
            className="border-0 shadow-sm hover:shadow-md transition-shadow cursor-pointer"
            onClick={() => budget.members && budget.members.length > 0 && openManageMembers(budget)}
          >
            <CardContent className="pt-6">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="font-semibold text-gray-900">{t.mockData[budget.name as keyof typeof t.mockData]}</h3>
                  <Badge variant="outline" className="mt-2">
                    {budget.type === 'personal' ? t.budgets.personal : budget.type === 'family' ? t.budgets.family : t.budgets.business}
                  </Badge>
                </div>
                {budget.members && budget.members.length > 0 && (
                  <div className="flex items-center gap-1 text-blue-600 bg-blue-50 px-2 py-1 rounded-lg">
                    <Users className="w-4 h-4" />
                    <span className="text-sm font-medium">{budget.members.length}</span>
                  </div>
                )}
              </div>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-500">{t.budgets.balance}</span>
                  <span className="text-2xl font-semibold text-gray-900">
                    ${budget.balance.toLocaleString()}
                  </span>
                </div>
              </div>
              {budget.members && budget.members.length > 0 && (
                <div className="mt-4 pt-4 border-t border-gray-100">
                  <p className="text-xs text-gray-500">{t.budgets.clickToManageMembers}</p>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Monthly Budget Overview */}
      <Card className="border-0 shadow-sm">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>{t.budgets.monthlyBudgetOverview}</CardTitle>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-500">March 2026</span>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-6">
            {/* Overall Progress */}
            <div className="p-4 bg-gradient-to-br from-blue-50 to-purple-50 rounded-xl">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <p className="text-sm text-gray-600">{t.budgets.totalSpending}</p>
                  <p className="text-2xl font-semibold text-gray-900 mt-1">
                    ${totalSpent.toLocaleString()} / ${totalAllocated.toLocaleString()}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-gray-600">{t.budgets.remaining}</p>
                  <p className="text-2xl font-semibold text-green-600 mt-1">
                    ${(totalAllocated - totalSpent).toLocaleString()}
                  </p>
                </div>
              </div>
              <Progress value={overallProgress} className="h-3" />
              <div className="flex items-center justify-between mt-2">
                <span className="text-sm text-gray-600">{overallProgress.toFixed(1)}% {t.budgets.used}</span>
                <div className="flex items-center gap-1">
                  {overallProgress > 85 ? (
                    <>
                      <AlertCircle className="w-4 h-4 text-orange-500" />
                      <span className="text-sm text-orange-600">{t.budgets.approachingLimit}</span>
                    </>
                  ) : (
                    <>
                      <TrendingUp className="w-4 h-4 text-green-500" />
                      <span className="text-sm text-green-600">{t.budgets.onTrack}</span>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* Category Budgets */}
            <div className="space-y-4">
              <h3 className="font-medium text-gray-900">{t.budgets.categories}</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {categoryBudgets.map((budget) => {
                  const progress = (budget.spent / budget.allocated) * 100;
                  const isOverBudget = progress >= 100;
                  const isWarning = progress >= 85 && progress < 100;

                  return (
                    <div key={budget.category} className="space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div
                            className="w-3 h-3 rounded-full"
                            style={{ backgroundColor: budget.color }}
                          />
                          <span className="font-medium text-gray-900">{translateCategory(budget.category)}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-600">
                            ${budget.spent} / ${budget.allocated}
                          </span>
                          {isOverBudget && (
                            <Badge variant="destructive" className="text-xs">
                              {t.budgets.over}
                            </Badge>
                          )}
                          {isWarning && (
                            <Badge variant="outline" className="text-xs text-orange-600 border-orange-300">
                              85%+
                            </Badge>
                          )}
                        </div>
                      </div>
                      <Progress
                        value={Math.min(progress, 100)}
                        className="h-2"
                        style={
                          {
                            '--progress-background': budget.color,
                          } as React.CSSProperties
                        }
                      />
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Quick Actions */}
            <div className="flex gap-3 pt-4">
              <Button variant="outline" className="flex-1">
                {t.budgets.adjustBudgets}
              </Button>
              <Button variant="outline" className="flex-1">
                {t.budgets.viewHistory}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Manage Members Dialog */}
      <Dialog open={manageMembersDialogOpen} onOpenChange={setManageMembersDialogOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Users className="w-5 h-5" />
              {t.budgets.manageMembers}
            </DialogTitle>
            <DialogDescription>
              {t.budgets.manageMembersDescription} {selectedBudget && t.mockData[selectedBudget.name as keyof typeof t.mockData]}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {/* Add Member Button */}
            <Button 
              size="sm" 
              variant="outline" 
              className="w-full"
              onClick={() => setAddMemberDialogOpen(true)}
            >
              <UserPlus className="w-4 h-4 mr-2" />
              {t.budgets.addMember}
            </Button>

            {/* Members List */}
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {selectedBudget?.members?.map((member) => (
                <div key={member.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
                  <div className="flex items-center gap-3">
                    <Avatar className="w-10 h-10">
                      <AvatarFallback className="bg-blue-100 text-blue-600">
                        {member.name.split(' ').map(n => n[0]).join('')}
                      </AvatarFallback>
                    </Avatar>
                    <div>
                      <div className="font-medium text-gray-900">{member.name}</div>
                      <div className="text-sm text-gray-500 flex items-center gap-1">
                        <Mail className="w-3 h-3" />
                        {member.email}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={member.role === 'owner' ? 'default' : 'outline'}>
                      {member.role === 'owner' && <Shield className="w-3 h-3 mr-1" />}
                      {member.role === 'owner' ? t.budgets.owner : member.role === 'editor' ? t.budgets.editor : t.budgets.viewer}
                    </Badge>
                    {member.role !== 'owner' && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button 
                            variant="ghost" 
                            size="sm" 
                            className="h-8 w-8 p-0"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <MoreVertical className="w-4 h-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleChangeRole(member.name, 'editor')}>
                            <Edit2 className="w-4 h-4 mr-2" />
                            {t.budgets.changeToEditor}
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => handleChangeRole(member.name, 'viewer')}>
                            <Edit2 className="w-4 h-4 mr-2" />
                            {t.budgets.changeToViewer}
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem 
                            className="text-red-600"
                            onClick={() => handleRemoveMember(member.name)}
                          >
                            <Trash2 className="w-4 h-4 mr-2" />
                            {t.budgets.removeMember}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <div className="flex justify-end pt-4 border-t">
              <Button variant="outline" onClick={() => setManageMembersDialogOpen(false)}>
                {t.common.close}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Add Member Dialog */}
      <Dialog open={addMemberDialogOpen} onOpenChange={setAddMemberDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <UserPlus className="w-5 h-5" />
              {t.budgets.addMember}
            </DialogTitle>
            <DialogDescription>
              {t.budgets.addMemberDescription}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleAddMember} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">{t.budgets.emailAddress}</Label>
              <Input
                id="email"
                name="email"
                type="email"
                placeholder={t.budgets.emailPlaceholder}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="role">{t.budgets.role}</Label>
              <Select name="role" defaultValue="viewer" required>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="editor">{t.budgets.editor} - {t.budgets.editorDescription}</SelectItem>
                  <SelectItem value="viewer">{t.budgets.viewer} - {t.budgets.viewerDescription}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-3 pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={() => setAddMemberDialogOpen(false)}
                className="flex-1"
              >
                {t.common.cancel}
              </Button>
              <Button type="submit" className="flex-1">
                <Mail className="w-4 h-4 mr-2" />
                {t.budgets.sendInvite}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}