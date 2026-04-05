export type BudgetType = 'personal' | 'family' | 'business';

export interface Budget {
  id: string;
  name: string;
  type: BudgetType;
  currency: string;
  balance: number;
  members?: BudgetMember[];
}

export interface BudgetMember {
  id: string;
  name: string;
  email: string;
  role: 'owner' | 'editor' | 'viewer';
  avatar?: string;
}

export type TransactionType = 'income' | 'expense';

export interface Transaction {
  id: string;
  budgetId: string;
  type: TransactionType;
  amount: number;
  currency: string;
  category: string;
  description: string;
  date: string;
  tags?: string[];
  recurring?: boolean;
  receiptUrl?: string;
}

export interface Category {
  id: string;
  name: string;
  icon: string;
  color: string;
  type: TransactionType;
}

export interface Goal {
  id: string;
  budgetId: string;
  name: string;
  targetAmount: number;
  currentAmount: number;
  currency: string;
  deadline?: string;
  color: string;
  icon: string;
  completed: boolean;
}

export interface Notification {
  id: string;
  title: string;
  message: string;
  type: 'warning' | 'info' | 'success';
  read: boolean;
  date: string;
}

export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  defaultCurrency: string;
  twoFactorEnabled: boolean;
  subscription: 'free' | 'pro';
}

export interface AIInsight {
  id: string;
  type: 'spending' | 'unusual' | 'prediction' | 'recommendation';
  title: string;
  description: string;
  date: string;
  priority: 'low' | 'medium' | 'high';
}
