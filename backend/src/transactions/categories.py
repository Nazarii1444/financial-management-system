from fastapi.exceptions import HTTPException

from src.models import TransactionKind

# ── Category lists ──────────────────────────────────────────────────────────

ALLOWED_EXPENSE_CATEGORIES = {
    "shopping", "food", "phone", "entertainment", "education",
    "beauty", "sports", "social", "transportation", "clothing",
    "car", "alcohol", "cigarettes", "electronics", "travel",
    "health", "pets", "repairs", "housing", "home", "gifts",
    "donations", "lottery", "kids", "utilities",
}

ALLOWED_INCOME_CATEGORIES = {
    "salary", "freelance", "investment", "gift", "bonus",
    "rental", "interest", "dividend", "business", "other",
}

ALLOWED_TRANSFER_CATEGORIES = {"transfer", "other"}

ALL_CATEGORIES = ALLOWED_EXPENSE_CATEGORIES | ALLOWED_INCOME_CATEGORIES | ALLOWED_TRANSFER_CATEGORIES


def validate_category(kind: TransactionKind, category_name: str) -> None:
    cat = category_name.strip().lower()
    if kind == TransactionKind.EXPENSE and cat not in ALLOWED_EXPENSE_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown expense category '{category_name}'. Allowed: {sorted(ALLOWED_EXPENSE_CATEGORIES)}",
        )
    if kind == TransactionKind.INCOME and cat not in ALLOWED_INCOME_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown income category '{category_name}'. Allowed: {sorted(ALLOWED_INCOME_CATEGORIES)}",
        )
