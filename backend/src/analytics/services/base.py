"""
BaseAnalyticsService
────────────────────
Abstract base for every analytics service in this module.

To add a new analytic:
  1. Create  src/analytics/services/<name>_service.py
  2. Subclass BaseAnalyticsService
  3. Implement  async def compute(self, **kwargs) -> Any
  4. Register the endpoint in analytics_router.py

The base class provides:
  - _convert(amount, from_currency) → Decimal  (USD-pivot conversion)
  - _signed(amount, kind) → Decimal             (positive income / negative expense)
  - self.target_currency                        (reporting currency, defaults to user's)
"""

from abc import ABC, abstractmethod
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import TransactionKind, User


class BaseAnalyticsService(ABC):
    def __init__(
        self,
        session: AsyncSession,
        user: User,
        rates: Dict[str, float],
        target_currency: Optional[str] = None,
    ) -> None:
        self.session = session
        self.user = user
        self.rates = rates
        self.target_currency = (target_currency or user.default_currency).upper()

    # ── Extension point ───────────────────────────────────────────────────────

    @abstractmethod
    async def compute(self, **kwargs) -> Any:
        """
        Main entry-point called by the router.
        Override with concrete analytics logic.
        """

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _convert(self, amount: Decimal, from_currency: str) -> Decimal:
        """
        Convert *amount* from *from_currency* → self.target_currency via USD pivot.
        Returns Decimal rounded to 2 dp.
        Silently returns 0 when a rate is missing (prevents endpoint crashes on
        currencies not yet loaded from NBU).
        """
        src = from_currency.strip().upper()
        dst = self.target_currency

        if src == dst:
            return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        src_rate = self.rates.get(src)
        dst_rate = self.rates.get(dst)
        if src_rate is None or dst_rate is None:
            return Decimal("0.00")

        usd = amount / Decimal(str(src_rate))
        converted = usd * Decimal(str(dst_rate))
        return converted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _signed(self, amount: Decimal, kind: TransactionKind) -> Decimal:
        """Positive for INCOME, negative for EXPENSE, zero for TRANSFER."""
        if kind == TransactionKind.INCOME:
            return amount
        if kind == TransactionKind.EXPENSE:
            return -amount
        return Decimal("0")

    def _effective_currency(self, tx_currency: Optional[str]) -> str:
        return (tx_currency or self.user.default_currency).strip().upper()

