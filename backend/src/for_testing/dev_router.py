import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import random
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models import User, Transaction, TransactionKind, Currencies
from src.utils.auth_services import hash_password

dev_router = APIRouter(tags=["Dev"])

@dev_router.post("/seed", status_code=status.HTTP_201_CREATED)
async def seed_database(session: AsyncSession = Depends(get_db)):
    """
    Creates 10 users and 20 transactions for each of them.
    Without auth, for local dev.
    """
    now = datetime.now(timezone.utc)

    users = []
    for i in range(1, 11):
        suffix = uuid.uuid4().hex[:6]
        username = f"user{i}_{suffix}"
        email = f"{username}@example.com"
        user = User(
            username=username,
            email=email,
            hashed_password=hash_password("password123"),
            default_currency=Currencies.USD.value,
            timezone="UTC",
            capital=0.0,
        )
        users.append(user)

    session.add_all(users)
    await session.flush()

    categories = ["Food", "Salary", "Transport", "Rent", "Shopping", "Health", "Entertainment", "Utilities"]
    currencies = [c.value for c in Currencies]

    txs = []
    for u in users:
        for _ in range(20):
            amount = Decimal(str(round(random.uniform(1, 1000), 2)))
            kind = random.choice(list(TransactionKind))
            category = random.choice(categories)
            currency = random.choice(currencies)

            delta = timedelta(
                days=random.randint(0, 120),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            dt = now - delta

            txs.append(Transaction(
                user_id=u.id_,
                amount=amount,
                kind=kind,
                category_name=category,
                currency=currency,
                date=dt,
            ))

    session.add_all(txs)
    await session.commit()

    return {
        "users_created": len(users),
        "transactions_created": len(txs),
        "example_user": {"id_": users[0].id_, "username": users[0].username, "email": users[0].email},
    }
