import { Car, Gift, Home, Laptop, Plane, Shield, Target } from 'lucide-react';

export const GOAL_ICONS = ['Shield', 'Plane', 'Laptop', 'Gift', 'Home', 'Car'] as const;
export const GOAL_COLORS = ['#3b82f6', '#10b981', '#8b5cf6', '#f59e0b', '#ec4899', '#06b6d4'];

const ICONS: Record<string, typeof Target> = { Shield, Plane, Laptop, Gift, Home, Car };

export function GoalIcon({ name, color, className = 'w-6 h-6' }: { name: string; color: string; className?: string }) {
  const Icon = ICONS[name] ?? Target;
  return <Icon className={className} style={{ color }} />;
}
