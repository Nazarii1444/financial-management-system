"""
Human-readable text for calendar events built from recurring rules.

Shared by the .ics feed and the Google Calendar sync so both show the same
"🏠 Оренда — 9 000 ₴" titles. Pure functions, no DB.
"""
from decimal import Decimal
from typing import Optional

from src.models import TransactionKind

SUPPORTED_LANGS = ("uk", "en")
DEFAULT_LANG = "uk"

CATEGORY_EMOJI = {
    # expense
    "shopping": "🛍️", "food": "🍽️", "phone": "📱", "entertainment": "🎬", "education": "📚",
    "beauty": "💄", "sports": "🏋️", "social": "👥", "transportation": "🚌", "clothing": "👕",
    "car": "🚗", "alcohol": "🍷", "cigarettes": "🚬", "electronics": "💻", "travel": "✈️",
    "health": "💊", "pets": "🐾", "repairs": "🔧", "housing": "🏠", "home": "🛋️",
    "gifts": "🎁", "donations": "🤝", "lottery": "🎰", "kids": "🧸", "utilities": "💡",
    # income
    "salary": "💰", "freelance": "💼", "investment": "📈", "gift": "🎁", "bonus": "🎉",
    "rental": "🏘️", "interest": "🏦", "dividend": "📊", "business": "🏢", "other": "💵",
    # transfer
    "transfer": "🔁",
}

CATEGORY_NAMES = {
    "uk": {
        "shopping": "Покупки", "food": "Їжа та ресторани", "phone": "Звʼязок та інтернет",
        "entertainment": "Розваги", "education": "Освіта", "beauty": "Краса", "sports": "Спорт",
        "social": "Соціальне життя", "transportation": "Транспорт", "clothing": "Одяг",
        "car": "Автомобіль", "alcohol": "Алкоголь", "cigarettes": "Сигарети",
        "electronics": "Електроніка", "travel": "Подорожі", "health": "Здоровʼя",
        "pets": "Домашні тварини", "repairs": "Ремонт", "housing": "Житло", "home": "Дім",
        "gifts": "Подарунки", "donations": "Благодійність", "lottery": "Лотерея", "kids": "Діти",
        "utilities": "Рахунки та комунальні", "salary": "Зарплата", "freelance": "Фриланс",
        "investment": "Інвестиції", "gift": "Подарунок", "bonus": "Бонус",
        "rental": "Дохід від оренди", "interest": "Відсотки", "dividend": "Дивіденди",
        "business": "Бізнес", "other": "Інше", "transfer": "Переказ",
    },
    "en": {
        "shopping": "Shopping", "food": "Food & Dining", "phone": "Phone & Internet",
        "entertainment": "Entertainment", "education": "Education", "beauty": "Beauty",
        "sports": "Sports", "social": "Social", "transportation": "Transportation",
        "clothing": "Clothing", "car": "Car", "alcohol": "Alcohol", "cigarettes": "Cigarettes",
        "electronics": "Electronics", "travel": "Travel", "health": "Health", "pets": "Pets",
        "repairs": "Repairs", "housing": "Housing", "home": "Home", "gifts": "Gifts",
        "donations": "Donations", "lottery": "Lottery", "kids": "Kids",
        "utilities": "Bills & Utilities", "salary": "Salary", "freelance": "Freelance",
        "investment": "Investment", "gift": "Gift", "bonus": "Bonus", "rental": "Rental income",
        "interest": "Interest", "dividend": "Dividends", "business": "Business", "other": "Other",
        "transfer": "Transfer",
    },
}

TEXT = {
    "uk": {
        "calendar_name": "FinanceHub — платежі",
        "calendar_description": "Регулярні платежі та доходи з FinanceHub",
        "category": "Категорія",
        "kind": {TransactionKind.EXPENSE: "Регулярна витрата", TransactionKind.INCOME: "Регулярний дохід",
                 TransactionKind.TRANSFER: "Регулярний переказ"},
        "note": "Нотатка",
        "tags": "Теги",
        "footer": "Створено FinanceHub. Змінюйте правило в застосунку — календар оновиться.",
        "reminder": "Завтра платіж",
    },
    "en": {
        "calendar_name": "FinanceHub — payments",
        "calendar_description": "Recurring payments and income from FinanceHub",
        "category": "Category",
        "kind": {TransactionKind.EXPENSE: "Recurring expense", TransactionKind.INCOME: "Recurring income",
                 TransactionKind.TRANSFER: "Recurring transfer"},
        "note": "Note",
        "tags": "Tags",
        "footer": "Created by FinanceHub. Edit the rule in the app and the calendar follows.",
        "reminder": "Payment tomorrow",
    },
}

CURRENCY_SYMBOLS = {"UAH": "₴", "USD": "$", "EUR": "€", "GBP": "£", "PLN": "zł", "JPY": "¥", "CHF": "CHF"}


def normalize_lang(lang: Optional[str]) -> str:
    lang = (lang or "").strip().lower()[:2]
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def format_amount(amount, currency: Optional[str], lang: str = DEFAULT_LANG) -> str:
    """9000 → '9 000 ₴'; 2100.5 → '2 100,50 ₴' (uk) / '$2,100.50' (en, USD)."""
    value = Decimal(str(amount)).quantize(Decimal("0.01"))
    whole = value == value.to_integral_value()
    text = f"{value:,.0f}" if whole else f"{value:,.2f}"
    if lang == "uk":
        text = text.replace(",", "\u00a0").replace(".", ",")   # NBSP between thousands
    code = (currency or "").upper()
    symbol = CURRENCY_SYMBOLS.get(code, code)
    if lang == "en" and code in ("USD", "GBP", "EUR", "JPY"):
        return f"{symbol}{text}"
    return f"{text} {symbol}".strip()


def event_title(rule, currency: str, lang: str = DEFAULT_LANG) -> str:
    emoji = CATEGORY_EMOJI.get((rule.category_name or "").lower(), "💳")
    sign = "+" if rule.kind == TransactionKind.INCOME else ""
    return f"{emoji} {rule.name} — {sign}{format_amount(rule.amount, currency, lang)}"


def event_description(rule, lang: str = DEFAULT_LANG) -> str:
    t = TEXT[lang]
    category = CATEGORY_NAMES[lang].get((rule.category_name or "").lower(), rule.category_name)
    lines = [t["kind"].get(rule.kind, ""), f"{t['category']}: {category}"]
    if rule.note:
        lines.append(f"{t['note']}: {rule.note}")
    if rule.tags:
        lines.append(f"{t['tags']}: {', '.join(rule.tags)}")
    lines += ["", t["footer"]]
    return "\n".join(lines)
