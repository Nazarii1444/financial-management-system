"""
MCC (Merchant Category Code, ISO 18245) → app category, plus kind detection.

Banks report the merchant type for every card payment, which classifies
expenses far more reliably than guessing from the merchant name. Ranges cover
the common groups; anything unknown falls back to "shopping" (expense) or
"other" (income). The user can change every row in the import preview.
"""
import re
from typing import Optional, Tuple

from src.models import TransactionKind

# (first, last, category) — inclusive ranges, checked in order
_MCC_RANGES = [
    (3000, 3299, "travel"),        # airlines
    (3351, 3441, "transportation"),  # car rental
    (3501, 3999, "travel"),        # hotels
    (4011, 4011, "transportation"),
    (4111, 4131, "transportation"),  # commuter transport, taxi, bus
    (4411, 4411, "travel"),        # cruises
    (4457, 4468, "travel"),
    (4511, 4582, "travel"),        # airlines, airports
    (4722, 4723, "travel"),        # travel agencies
    (4784, 4784, "car"),           # tolls, road fees
    (4789, 4789, "transportation"),
    (4812, 4816, "phone"),         # telecom, internet
    (4899, 4899, "phone"),         # cable / streaming TV
    (4900, 4900, "utilities"),
    (5013, 5013, "car"),
    (5045, 5045, "electronics"),
    (5122, 5122, "health"),
    (5200, 5261, "repairs"),       # home supply, hardware, paint, garden
    (5300, 5311, "shopping"),
    (5331, 5399, "shopping"),
    (5411, 5499, "food"),          # groceries, bakeries, convenience
    (5511, 5599, "car"),           # dealers, parts, fuel (5541/5542)
    (5611, 5699, "clothing"),
    (5712, 5719, "home"),          # furniture, home furnishings
    (5722, 5722, "home"),          # household appliances
    (5732, 5735, "electronics"),
    (5811, 5814, "food"),          # restaurants, cafes, fast food
    (5815, 5818, "entertainment"),  # digital goods, games, subscriptions
    (5912, 5912, "health"),        # pharmacies
    (5921, 5921, "alcohol"),
    (5940, 5941, "sports"),
    (5942, 5943, "education"),     # books, stationery
    (5945, 5945, "kids"),          # toys
    (5946, 5946, "electronics"),
    (5947, 5947, "gifts"),
    (5977, 5977, "beauty"),
    (5992, 5992, "gifts"),         # florists
    (5993, 5993, "cigarettes"),
    (5995, 5995, "pets"),
    (5999, 5999, "shopping"),
    (7011, 7033, "travel"),        # hotels, campgrounds
    (7210, 7221, "home"),          # laundry, photo
    (7230, 7230, "beauty"),
    (7297, 7298, "beauty"),        # massage, spa
    (7349, 7349, "repairs"),
    (7512, 7519, "transportation"),
    (7523, 7549, "car"),           # parking, car service, car wash
    (7832, 7841, "entertainment"),  # cinema, video
    (7911, 7994, "entertainment"),
    (7995, 7995, "lottery"),
    (7996, 7999, "entertainment"),
    (8011, 8099, "health"),        # doctors, dentists, labs
    (8211, 8299, "education"),
    (8398, 8398, "donations"),
    (8661, 8661, "donations"),
    (9311, 9399, "utilities"),     # taxes, government services
    (742, 742, "pets"),            # veterinary
    (1520, 1799, "repairs"),       # contractors
]

# Money movement rather than spending
TRANSFER_MCC = {"4829", "6010", "6011", "6012", "6050", "6051", "6538", "6540"}

_OWN_TRANSFER = re.compile(
    r"^(з|на|у|в)\s+(банк[уи]|чорн|біл|гривнев|доларов|євров|рахун|картк|скарбничк)|переказ між своїми|"
    r"поповнення банки|^зі\s+скарбнички",
    re.IGNORECASE,
)
_SALARY = re.compile(r"зарплат|заробітн|salary|payroll|аванс", re.IGNORECASE)
_CASHBACK = re.compile(r"кешбек|cashback|кешбэк", re.IGNORECASE)
_INTEREST = re.compile(r"відсотк|interest|депозит", re.IGNORECASE)


def category_for_mcc(mcc: Optional[str]) -> Optional[str]:
    try:
        code = int(str(mcc).strip())
    except (TypeError, ValueError):
        return None
    for first, last, category in _MCC_RANGES:
        if first <= code <= last:
            return category
    return None


def classify(amount_sign: int, mcc: Optional[str], description: str) -> Tuple[TransactionKind, str]:
    """(kind, category) for a statement row; *amount_sign* is −1 for debits."""
    mcc = (mcc or "").strip()
    if _OWN_TRANSFER.search(description or ""):
        return TransactionKind.TRANSFER, "transfer"
    if amount_sign < 0:
        if mcc in TRANSFER_MCC:
            return TransactionKind.TRANSFER, "transfer"
        return TransactionKind.EXPENSE, category_for_mcc(mcc) or "shopping"
    if _CASHBACK.search(description or ""):
        return TransactionKind.INCOME, "bonus"
    if _SALARY.search(description or ""):
        return TransactionKind.INCOME, "salary"
    if _INTEREST.search(description or ""):
        return TransactionKind.INCOME, "interest"
    return TransactionKind.INCOME, "other"
