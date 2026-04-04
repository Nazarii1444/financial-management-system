from src.config import NBU_API_URL
from typing import Dict
from sqlalchemy import select
from fastapi import APIRouter, HTTPException, status, Depends, FastAPI, Path
import httpx
from src.database import AsyncSessionLocal

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy.dialects.postgresql import insert

from fastapi_utilities import repeat_every
from src.config import logger
from src.database import get_db
from src.models import Currency

currency_router = APIRouter()


async def fetch_rates_from_nbu() -> Dict[str, float]:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(NBU_API_URL)
            r.raise_for_status()
            data = r.json()
    except httpx.TimeoutException as e:
        logger.error("NBU timeout: %s", e)
        raise HTTPException(status_code=504, detail="Rates provider timeout") from e
    except httpx.HTTPStatusError as e:
        logger.error("NBU HTTP error: %s", e)
        raise HTTPException(status_code=502, detail="Rates provider error") from e
    except Exception as e:
        logger.exception("NBU unexpected error")
        raise HTTPException(status_code=500, detail="Failed to fetch rates") from e

    usd_item = next((x for x in data if str(x.get("cc", "")).upper() == "USD"), None)
    if not usd_item or not usd_item.get("rate"):
        raise HTTPException(status_code=502, detail="USD rate not found in NBU response")

    usd_uah = float(usd_item["rate"])

    result: Dict[str, float] = {"USD": 1.0, "UAH": usd_uah}

    for item in data:
        code = str(item.get("cc", "")).upper()
        rate_uah = item.get("rate")
        if not code or rate_uah is None:
            continue
        if code in ("USD", "UAH"):
            continue
        try:
            rate_uah = float(rate_uah)
            if rate_uah <= 0:
                continue
            result[code] = usd_uah / rate_uah
        except (TypeError, ValueError):
            continue

    return result


async def upsert_rates(session: AsyncSession, rates: Dict[str, float]) -> int:
    if not rates:
        return 0
    values = [{"name": code, "rate": float(rate)} for code, rate in rates.items()]
    stmt = insert(Currency).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Currency.name],
        set_={"rate": stmt.excluded.rate},
    )
    await session.execute(stmt)
    return len(values)


def register_currency_cron(app: FastAPI) -> None:
    @app.on_event("startup")
    @repeat_every(seconds=60*60, wait_first=False, logger=logger)
    async def scheduled_refresh() -> None:
        async with AsyncSessionLocal() as session:
            try:
                rates = await fetch_rates_from_nbu()
                updated = await upsert_rates(session, rates)
                await session.commit()
                logger.info("Currencies refreshed: %s rows updated", updated)
            except Exception:
                logger.exception("Currencies refresh failed")


@currency_router.get("/{code}", response_model=float, status_code=status.HTTP_200_OK)
async def get_rate_by_code(
    code: str = Path(..., min_length=3, max_length=3, description="ISO 4217 code, e.g. UAH, EUR"),
    session: AsyncSession = Depends(get_db),
) -> float:
    code = code.upper()
    if code == "USD":
        return 1.0

    stmt = select(Currency.rate).where(Currency.name == code)
    res = await session.execute(stmt)
    rate = res.scalar_one_or_none()
    if rate is None:
        raise HTTPException(status_code=404, detail="Currency not found")
    return float(rate)


@currency_router.get("", response_model=Dict[str, float], status_code=status.HTTP_200_OK)
async def get_rates(
    session: AsyncSession = Depends(get_db),
) -> Dict[str, float]:
    result = await session.execute(select(Currency.name, Currency.rate))
    rates = {name: float(rate) for name, rate in result.all()}
    rates.setdefault("USD", 1.0)
    return rates
