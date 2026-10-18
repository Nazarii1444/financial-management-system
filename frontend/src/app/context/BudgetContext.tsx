import { createContext, useCallback, useContext, useMemo, useState, ReactNode } from 'react';
import { budgetsApi } from '../lib/api';
import { useApi } from '../hooks/useApi';
import type { BudgetOut } from '../types/api';

const SELECTED_KEY = 'fms.selectedBudget';

interface BudgetContextType {
  budgets: BudgetOut[];
  loading: boolean;
  error: unknown;
  selectedBudget: BudgetOut | null;
  selectBudget: (id: number) => void;
  reload: () => void;
}

const BudgetContext = createContext<BudgetContextType | undefined>(undefined);

export function BudgetProvider({ children }: { children: ReactNode }) {
  const { data, loading, error, reload } = useApi(() => budgetsApi.list(), []);
  const [selectedId, setSelectedId] = useState<number | null>(() => {
    try {
      const raw = localStorage.getItem(SELECTED_KEY);
      return raw ? Number(raw) : null;
    } catch {
      return null;
    }
  });

  const selectBudget = useCallback((id: number) => {
    setSelectedId(id);
    try {
      localStorage.setItem(SELECTED_KEY, String(id));
    } catch {
      // ignore
    }
  }, []);

  const value = useMemo<BudgetContextType>(() => {
    const budgets = data ?? [];
    // Fall back to the first budget if the saved one was deleted / is not ours
    const selectedBudget = budgets.find((b) => b.id_ === selectedId) ?? budgets[0] ?? null;
    return { budgets, loading, error, selectedBudget, selectBudget, reload };
  }, [data, loading, error, selectedId, selectBudget, reload]);

  return <BudgetContext.Provider value={value}>{children}</BudgetContext.Provider>;
}

export function useBudgets() {
  const context = useContext(BudgetContext);
  if (context === undefined) {
    throw new Error('useBudgets must be used within a BudgetProvider');
  }
  return context;
}
