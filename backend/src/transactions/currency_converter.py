from typing import Dict, Union
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import Currency, TransactionKind
from decimal import Decimal, ROUND_HALF_UP



async def get_rates_map(session: AsyncSession, ensure_usd: bool = True) -> Dict[str, float]:
    result = await session.execute(select(Currency.name, Currency.rate))
    rates = {name: float(rate) for name, rate in result.all()}
    if ensure_usd and "USD" not in rates:
        rates["USD"] = 1.0
    return rates


async def convert_to_user_currency(
    session: AsyncSession,
    user_default_currency: str,                 # "EUR"
    kind: TransactionKind,                      # EXPENSE / INCOME
    amount: Union[float, Decimal],              # 123.5
    transaction_currency: str,                  # "UAH"
) -> Decimal:
    rates = await get_rates_map(session)
    src = transaction_currency.strip().upper()
    dst = user_default_currency.strip().upper()

    if src not in rates:
        raise ValueError(f"Rate for source currency '{src}' not found")
    if dst not in rates:
        raise ValueError(f"Rate for target currency '{dst}' not found")

    amt = Decimal(str(amount))
    if src == dst:
        converted = amt
    else:
        usd = amt / Decimal(str(rates[src]))
        converted = usd * Decimal(str(rates[dst]))

    converted = converted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if kind == TransactionKind.EXPENSE:
        converted = -converted

    return converted
