import { useState } from 'react';
import { Plus, Search, Filter, ArrowUpCircle, ArrowDownCircle, Download } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { mockTransactions, categories } from '../data/mockData';
import { Transaction, TransactionType } from '../types';
import { useLanguage } from '../i18n/LanguageContext';

export function Transactions() {
  const { t, translateCategory } = useLanguage();
  const [transactions, setTransactions] = useState(mockTransactions);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<'all' | TransactionType>('all');
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);

  const filteredTransactions = transactions.filter((transaction) => {
    const translatedDescription = t.mockData[transaction.description as keyof typeof t.mockData] || transaction.description;
    const translatedCategory = translateCategory(transaction.category);
    
    const matchesSearch =
      translatedDescription.toLowerCase().includes(searchQuery.toLowerCase()) ||
      translatedCategory.toLowerCase().includes(searchQuery.toLowerCase()) ||
      transaction.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      transaction.category.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = filterType === 'all' || transaction.type === filterType;
    return matchesSearch && matchesType;
  });

  const handleAddTransaction = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    
    const newTransaction: Transaction = {
      id: String(transactions.length + 1),
      budgetId: '1',
      type: formData.get('type') as TransactionType,
      amount: Number(formData.get('amount')),
      currency: 'USD',
      category: formData.get('category') as string,
      description: formData.get('description') as string,
      date: formData.get('date') as string,
      recurring: formData.get('recurring') === 'on',
    };

    setTransactions([newTransaction, ...transactions]);
    setIsAddDialogOpen(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">{t.transactions.title}</h1>
          <p className="text-sm text-gray-500 mt-1">{t.transactions.manageIncomeExpenses}</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm">
            <Download className="w-4 h-4 mr-2" />
            {t.transactions.export}
          </Button>
          <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="w-4 h-4 mr-2" />
                {t.transactions.addTransaction}
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>{t.transactions.addNewTransaction}</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleAddTransaction} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="type">{t.transactions.type}</Label>
                  <Select name="type" defaultValue="expense" required>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="income">{t.transactions.income}</SelectItem>
                      <SelectItem value="expense">{t.transactions.expense}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="amount">{t.transactions.amount}</Label>
                  <Input
                    id="amount"
                    name="amount"
                    type="number"
                    step="0.01"
                    placeholder="0.00"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="category">{t.transactions.category}</Label>
                  <Select name="category" required>
                    <SelectTrigger>
                      <SelectValue placeholder={t.transactions.selectCategory} />
                    </SelectTrigger>
                    <SelectContent>
                      {categories.map((cat) => (
                        <SelectItem key={cat.id} value={cat.name}>
                          {translateCategory(cat.name)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="description">{t.transactions.description}</Label>
                  <Textarea
                    id="description"
                    name="description"
                    placeholder={t.transactions.descriptionPlaceholder}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="date">{t.transactions.date}</Label>
                  <Input
                    id="date"
                    name="date"
                    type="date"
                    defaultValue={new Date().toISOString().split('T')[0]}
                    required
                  />
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="recurring"
                    name="recurring"
                    className="rounded"
                  />
                  <Label htmlFor="recurring" className="text-sm cursor-pointer">
                    {t.transactions.recurringTransaction}
                  </Label>
                </div>
                <div className="flex gap-3 pt-4">
                  <Button type="button" variant="outline" onClick={() => setIsAddDialogOpen(false)} className="flex-1">
                    {t.common.cancel}
                  </Button>
                  <Button type="submit" className="flex-1">
                    {t.transactions.addTransaction}
                  </Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Filters */}
      <Card className="border-0 shadow-sm">
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
              <Input
                placeholder={t.transactions.searchPlaceholder}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
            <Select value={filterType} onValueChange={(value: any) => setFilterType(value)}>
              <SelectTrigger className="w-full md:w-[180px]">
                <Filter className="w-4 h-4 mr-2" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t.transactions.allTransactions}</SelectItem>
                <SelectItem value="income">{t.transactions.incomeOnly}</SelectItem>
                <SelectItem value="expense">{t.transactions.expensesOnly}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Transactions List */}
      <Card className="border-0 shadow-sm">
        <CardHeader>
          <CardTitle>
            {filteredTransactions.length} {filteredTransactions.length !== 1 ? t.transactions.transactions : t.transactions.transaction}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {filteredTransactions.map((transaction) => (
              <div
                key={transaction.id}
                className="flex items-center justify-between p-4 rounded-lg border border-gray-100 hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-center gap-4">
                  <div
                    className={`w-12 h-12 rounded-full flex items-center justify-center ${
                      transaction.type === 'income' ? 'bg-green-100' : 'bg-red-100'
                    }`}
                  >
                    {transaction.type === 'income' ? (
                      <ArrowUpCircle className="w-6 h-6 text-green-600" />
                    ) : (
                      <ArrowDownCircle className="w-6 h-6 text-red-600" />
                    )}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="font-medium text-gray-900">
                        {t.mockData[transaction.description as keyof typeof t.mockData]}
                      </h4>
                      {transaction.recurring && (
                        <Badge variant="outline" className="text-xs">
                          {t.dashboard.recurring}
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-sm text-gray-500">{translateCategory(transaction.category)}</span>
                      {transaction.tags && transaction.tags.length > 0 && (
                        <>
                          <span className="text-gray-300">•</span>
                          <div className="flex gap-1">
                            {transaction.tags.map((tag) => (
                              <Badge key={tag} variant="secondary" className="text-xs">
                                {t.mockData[tag as keyof typeof t.mockData] || tag}
                              </Badge>
                            ))}
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <p
                    className={`text-lg font-semibold ${
                      transaction.type === 'income' ? 'text-green-600' : 'text-red-600'
                    }`}
                  >
                    {transaction.type === 'income' ? '+' : '-'}$
                    {transaction.amount.toLocaleString()}
                  </p>
                  <p className="text-sm text-gray-500 mt-1">{transaction.date}</p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}