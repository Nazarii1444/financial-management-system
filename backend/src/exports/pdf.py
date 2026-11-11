"""
PDF rendering of the reports in `reports.py` (fpdf2, A4 portrait).

Needs a TrueType font with Cyrillic. Lookup order: PDF_FONT_PATH /
PDF_FONT_BOLD_PATH env vars → DejaVu Sans (Debian `fonts-dejavu-core`, see
Dockerfile) → Arial (Windows / macOS). `fpdf2` is imported lazily so the API
still starts without it; the endpoints then answer 501.
"""
import os
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Sequence, Tuple

from src.calendar_export.formatting import CATEGORY_NAMES, format_amount, normalize_lang
from src.models import TransactionKind

_FONT_CANDIDATES: List[Tuple[str, str]] = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
]

# Palette (RGB)
INK = (17, 24, 39)
MUTED = (107, 114, 128)
LINE = (229, 231, 235)
ZEBRA = (249, 250, 251)
BRAND = (37, 99, 235)
GREEN = (22, 163, 74)
RED = (220, 38, 38)
AMBER = (217, 119, 6)
TILE = (243, 244, 246)

TEXT = {
    "uk": {
        "generated": "Сформовано {date}",
        "page": "Сторінка {page} з {{nb}}",
        "statement": "Місячна виписка",
        "expenses": "Структура витрат",
        "budgets": "Виконання бюджетів",
        "recurring": "Регулярні платежі",
        "opening": "Початковий баланс",
        "closing": "Кінцевий баланс",
        "income": "Доходи",
        "expense": "Витрати",
        "transactions": "Транзакцій: {n}",
        "date": "Дата", "name": "Назва", "category": "Категорія", "amount": "Сума",
        "in_currency": "У {cur}", "share": "Частка", "count": "К-сть", "change": "Зміна",
        "no_data": "За цей період даних немає.",
        "approx": "Суми в іншій валюті перераховано за поточним курсом НБУ; баланси на початок і кінець місяця обчислено від поточного балансу.",
        "total": "Разом",
        "vs_previous": "Попередній період: {amount}",
        "top": "Найбільші витрати",
        "budget": "Бюджет", "limit": "Ліміт", "spent": "Витрачено", "left": "Залишок", "used": "Виконання",
        "no_limit": "без ліміту", "over": "перевищено ліміт",
        "no_budgets": "У вас ще немає бюджетів.",
        "frequency": "Частота", "per_month": "На місяць", "per_year": "На рік", "next": "Наступний",
        "recurring_expenses": "Регулярні витрати", "recurring_incomes": "Регулярні доходи",
        "year_cost": "Регулярні витрати на рік",
        "month_cost": "≈ {amount} на місяць",
        "subs_year": "Підписки на рік",
        "subs_note": "Підписок: {n}",
        "by_category": "За категоріями",
        "approx_fx": "Суми в іншій валюті перераховано за поточним курсом НБУ.",
        "income_share": "Частка доходу",
        "income_share_note": "від регулярних доходів",
        "callout": "Ваші регулярні платежі коштують {year} на рік — це {month} щомісяця ще до будь-яких інших витрат.",
        "no_recurring": "Активних регулярних платежів немає.",
        "freq": {"DAILY": "Щодня", "WEEKLY": "Щотижня", "BIWEEKLY": "Раз на 2 тижні", "MONTHLY": "Щомісяця", "YEARLY": "Щороку"},
        "kind": {TransactionKind.EXPENSE: "Витрата", TransactionKind.INCOME: "Дохід", TransactionKind.TRANSFER: "Переказ"},
    },
    "en": {
        "generated": "Generated {date}",
        "page": "Page {page} of {{nb}}",
        "statement": "Monthly statement",
        "expenses": "Expense structure",
        "budgets": "Budget performance",
        "recurring": "Recurring payments",
        "opening": "Opening balance",
        "closing": "Closing balance",
        "income": "Income",
        "expense": "Expenses",
        "transactions": "Transactions: {n}",
        "date": "Date", "name": "Name", "category": "Category", "amount": "Amount",
        "in_currency": "In {cur}", "share": "Share", "count": "Count", "change": "Change",
        "no_data": "No data for this period.",
        "approx": "Amounts in other currencies use current NBU rates; opening and closing balances are derived from the current balance.",
        "total": "Total",
        "vs_previous": "Previous period: {amount}",
        "top": "Largest expenses",
        "budget": "Budget", "limit": "Limit", "spent": "Spent", "left": "Left", "used": "Used",
        "no_limit": "no limit", "over": "over the limit",
        "no_budgets": "You have no budgets yet.",
        "frequency": "Frequency", "per_month": "Per month", "per_year": "Per year", "next": "Next",
        "recurring_expenses": "Recurring expenses", "recurring_incomes": "Recurring income",
        "year_cost": "Recurring costs per year",
        "month_cost": "≈ {amount} per month",
        "subs_year": "Subscriptions per year",
        "subs_note": "Subscriptions: {n}",
        "by_category": "By category",
        "approx_fx": "Amounts in other currencies use current NBU rates.",
        "income_share": "Share of income",
        "income_share_note": "of recurring income",
        "callout": "Your recurring payments cost {year} a year — that is {month} every month before any other spending.",
        "no_recurring": "No active recurring payments.",
        "freq": {"DAILY": "Daily", "WEEKLY": "Weekly", "BIWEEKLY": "Every 2 weeks", "MONTHLY": "Monthly", "YEARLY": "Yearly"},
        "kind": {TransactionKind.EXPENSE: "Expense", TransactionKind.INCOME: "Income", TransactionKind.TRANSFER: "Transfer"},
    },
}

MONTHS = {
    "uk": ["січень", "лютий", "березень", "квітень", "травень", "червень", "липень", "серпень",
           "вересень", "жовтень", "листопад", "грудень"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
}


class PdfUnavailable(RuntimeError):
    pass


def find_fonts() -> Tuple[str, str]:
    regular, bold = os.getenv("PDF_FONT_PATH"), os.getenv("PDF_FONT_BOLD_PATH")
    if regular and os.path.exists(regular):
        return regular, bold if bold and os.path.exists(bold) else regular
    for reg, bld in _FONT_CANDIDATES:
        if os.path.exists(reg):
            return reg, bld if os.path.exists(bld) else reg
    raise PdfUnavailable("No TrueType font with Cyrillic found (install fonts-dejavu-core or set PDF_FONT_PATH)")


def _fmt_date(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime("%d.%m.%Y")


def period_label(start: datetime, end: datetime, lang: str) -> str:
    if start.day == 1 and (end.date() - start.date()).days in range(27, 31) and start.month == end.month:
        return f"{MONTHS[lang][start.month - 1].capitalize()} {start.year}"
    return f"{_fmt_date(start)} — {_fmt_date(end)}"


class _Doc:
    """Small layout helper over FPDF with the report's visual language."""

    def __init__(self, lang: str, title: str, subtitle: str, user_name: str, password: Optional[str] = None):
        try:
            from fpdf import FPDF
            from fpdf.enums import XPos, YPos
        except ImportError as exc:  # pragma: no cover - depends on the environment
            raise PdfUnavailable("fpdf2 is not installed (pip install -r requirements.txt)") from exc

        self.XPos, self.YPos = XPos, YPos
        self.password = password
        self.lang = lang
        self.t = TEXT[lang]
        regular, bold = find_fonts()
        t = self.t
        generated = t["generated"].format(date=datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC"))

        class _PDF(FPDF):
            def footer(inner):
                inner.set_y(-12)
                inner.set_font("Main", "", 7.5)
                inner.set_text_color(*MUTED)
                inner.cell(0, 5, f"FinanceHub · {user_name} · {generated}", align="L")
                inner.set_x(inner.l_margin)
                inner.cell(0, 5, t["page"].format(page=inner.page_no()), align="R")

        pdf = _PDF(format="A4", unit="mm")
        pdf.set_margins(15, 15, 15)
        pdf.set_auto_page_break(True, margin=18)
        pdf.add_font("Main", "", regular)
        pdf.add_font("Main", "B", bold)
        pdf.set_title(title)
        pdf.set_author("FinanceHub")
        pdf.add_page()
        self.pdf = pdf

        # Header: brand strip + title
        pdf.set_fill_color(*BRAND)
        pdf.rect(0, 0, 210, 4, style="F")
        pdf.set_y(12)
        self.text("FINANCEHUB", 8, bold=True, color=BRAND)
        self.text(title, 20, bold=True, h=10)
        self.text(subtitle, 10, color=MUTED, h=6)
        pdf.ln(4)

    # ── primitives ────────────────────────────────────────────────────────────

    @property
    def width(self) -> float:
        return self.pdf.w - self.pdf.l_margin - self.pdf.r_margin

    def text(self, value: str, size: float = 9.5, bold: bool = False, color=INK, h: float = 5, align: str = "L"):
        self.pdf.set_font("Main", "B" if bold else "", size)
        self.pdf.set_text_color(*color)
        self.pdf.multi_cell(0, h, value, align=align, new_x=self.XPos.LMARGIN, new_y=self.YPos.NEXT)

    def heading(self, value: str):
        self.ensure(16)
        self.pdf.ln(3)
        self.text(value, 12.5, bold=True, h=7)
        self.pdf.set_draw_color(*LINE)
        y = self.pdf.get_y()
        self.pdf.line(self.pdf.l_margin, y, self.pdf.l_margin + self.width, y)
        self.pdf.ln(2)

    def ensure(self, height: float):
        if self.pdf.get_y() + height > self.pdf.page_break_trigger:
            self.pdf.add_page()

    def fit(self, value: str, width: float) -> str:
        value = (value or "").replace("\n", " ")
        if self.pdf.get_string_width(value) <= width - 2:
            return value
        while value and self.pdf.get_string_width(value + "…") > width - 2:
            value = value[:-1]
        return value + "…"

    def money(self, amount, currency: Optional[str] = None, signed: bool = False) -> str:
        amount = Decimal(str(amount))
        text = format_amount(abs(amount), currency, self.lang)
        if signed and amount != 0:
            return ("+" if amount > 0 else "−") + text
        return ("−" + text) if amount < 0 else text

    def tiles(self, items: Sequence[Tuple[str, str, Optional[Tuple[int, int, int]], Optional[str]]]):
        """KPI tiles: (label, value, value colour, note)."""
        gap = 4
        w = (self.width - gap * (len(items) - 1)) / len(items)
        self.ensure(26)
        x0, y0 = self.pdf.l_margin, self.pdf.get_y()
        for i, (label, value, color, note) in enumerate(items):
            x = x0 + i * (w + gap)
            self.pdf.set_fill_color(*TILE)
            self.pdf.rect(x, y0, w, 22, style="F")
            self.pdf.set_xy(x + 3, y0 + 3)
            self.pdf.set_font("Main", "", 7.5)
            self.pdf.set_text_color(*MUTED)
            self.pdf.cell(w - 6, 4, self.fit(label, w - 6))
            self.pdf.set_xy(x + 3, y0 + 8)
            self.pdf.set_font("Main", "B", 12.5 if len(items) < 4 else 11)
            self.pdf.set_text_color(*(color or INK))
            self.pdf.cell(w - 6, 6, self.fit(value, w - 6))
            if note:
                self.pdf.set_xy(x + 3, y0 + 15)
                self.pdf.set_font("Main", "", 7)
                self.pdf.set_text_color(*MUTED)
                self.pdf.cell(w - 6, 4, self.fit(note, w - 6))
        self.pdf.set_xy(x0, y0 + 26)

    def table(self, columns: Sequence[Tuple[str, float, str]], rows: Sequence[Sequence], colors=None, bold_last=False):
        """columns: (title, width fraction, align). rows: cell strings. colors: per-row per-cell RGB or None."""
        widths = [self.width * frac for _, frac, _ in columns]

        def header():
            self.pdf.set_font("Main", "B", 8)
            self.pdf.set_text_color(*MUTED)
            self.pdf.set_fill_color(*TILE)
            for (title, _, align), w in zip(columns, widths):
                self.pdf.cell(w, 7, self.fit(title, w), align=align, fill=True)
            self.pdf.ln(7)

        self.ensure(16)
        header()
        for index, row in enumerate(rows):
            if self.pdf.get_y() + 6.5 > self.pdf.page_break_trigger:
                self.pdf.add_page()
                header()
            last = bold_last and index == len(rows) - 1
            self.pdf.set_font("Main", "B" if last else "", 8.5)
            fill = index % 2 == 1 and not last
            self.pdf.set_fill_color(*ZEBRA)
            for col, ((_, _, align), w, value) in enumerate(zip(columns, widths, row)):
                color = colors[index][col] if colors and colors[index] and colors[index][col] else INK
                self.pdf.set_text_color(*color)
                self.pdf.cell(w, 6.5, self.fit(str(value), w), align=align, fill=fill)
            self.pdf.ln(6.5)
            if last:
                pass
        self.pdf.ln(2)

    def bar_rows(self, rows: Sequence[Tuple[str, float, str, Tuple[int, int, int]]], max_value: float):
        """Horizontal bars: (label, value, value text, colour)."""
        label_w, value_w = self.width * 0.3, self.width * 0.22
        bar_w = self.width - label_w - value_w - 4
        for label, value, value_text, color in rows:
            self.ensure(8)
            y = self.pdf.get_y()
            self.pdf.set_font("Main", "", 8.5)
            self.pdf.set_text_color(*INK)
            self.pdf.cell(label_w, 6, self.fit(label, label_w))
            x = self.pdf.get_x() + 2
            self.pdf.set_fill_color(*TILE)
            self.pdf.rect(x, y + 1.5, bar_w, 3, style="F")
            if max_value > 0 and value > 0:
                self.pdf.set_fill_color(*color)
                self.pdf.rect(x, y + 1.5, max(0.8, bar_w * min(value, max_value) / max_value), 3, style="F")
            self.pdf.set_x(x + bar_w + 2)
            self.pdf.cell(value_w, 6, value_text, align="R")
            self.pdf.ln(7)

    def note(self, value: str):
        self.pdf.ln(2)
        self.text(value, 7.5, color=MUTED, h=4)

    def callout(self, value: str):
        self.ensure(18)
        self.pdf.ln(1)
        y = self.pdf.get_y()
        self.pdf.set_fill_color(254, 243, 199)
        self.pdf.set_font("Main", "B", 10)
        lines = len(self.pdf.multi_cell(self.width - 10, 5.5, value, align="L", dry_run=True, output="LINES"))
        h = lines * 5.5 + 8
        self.pdf.rect(self.pdf.l_margin, y, self.width, h, style="F")
        self.pdf.set_fill_color(*AMBER)
        self.pdf.rect(self.pdf.l_margin, y, 1.5, h, style="F")
        self.pdf.set_xy(self.pdf.l_margin + 6, y + 4)
        self.pdf.set_text_color(120, 53, 15)
        self.pdf.multi_cell(self.width - 10, 5.5, value, align="L", new_x=self.XPos.LMARGIN, new_y=self.YPos.NEXT)
        self.pdf.set_y(y + h + 3)

    def output(self) -> bytes:
        if self.password:
            from fpdf.enums import EncryptionMethod
            # Readers ask for the user password; the owner password is random and thrown away
            self.pdf.set_encryption(
                owner_password=secrets.token_urlsafe(24), user_password=self.password,
                encryption_method=EncryptionMethod.AES_256, encrypt_metadata=True,
            )
        return bytes(self.pdf.output())


def _cat(lang: str, category: str) -> str:
    return CATEGORY_NAMES[lang].get(category, category)


# ── Reports ───────────────────────────────────────────────────────────────────

def render_statement(data: dict, user_name: str, lang: Optional[str] = None, password: Optional[str] = None) -> bytes:
    lang = normalize_lang(lang)
    cur = data["currency"]
    doc = _Doc(lang, TEXT[lang]["statement"], f"{period_label(data['start'], data['end'], lang)} · {cur}", user_name, password)
    t = doc.t
    doc.tiles([
        (t["opening"], doc.money(data["opening"], cur), None, None),
        (t["income"], doc.money(data["income"], cur, signed=True), GREEN, None),
        (t["expense"], doc.money(-data["expense"], cur, signed=True), RED, None),
        (t["closing"], doc.money(data["closing"], cur), None, t["transactions"].format(n=data["count"])),
    ])
    if not data["rows"]:
        doc.text(t["no_data"], color=MUTED)
    else:
        rows, colors = [], []
        for r in data["rows"]:
            original = doc.money(r["amount"], r["currency"])
            converted = doc.money(r["converted"], cur, signed=r["kind"] != TransactionKind.TRANSFER)
            color = GREEN if r["kind"] == TransactionKind.INCOME else RED if r["kind"] == TransactionKind.EXPENSE else MUTED
            rows.append([_fmt_date(r["date"]), r["name"], _cat(lang, r["category"]), original, converted])
            colors.append([None, None, MUTED, MUTED, color])
        net = data["income"] - data["expense"]
        rows.append([t["total"], "", "", "", doc.money(net, cur, signed=True)])
        colors.append([None, None, None, None, GREEN if net >= 0 else RED])
        doc.table(
            [(t["date"], 0.14, "L"), (t["name"], 0.33, "L"), (t["category"], 0.21, "L"),
             (t["amount"], 0.15, "R"), (t["in_currency"].format(cur=cur), 0.17, "R")],
            rows, colors, bold_last=True,
        )
    doc.note(t["approx"])
    return doc.output()


def render_expenses(data: dict, user_name: str, lang: Optional[str] = None, password: Optional[str] = None) -> bytes:
    lang = normalize_lang(lang)
    cur = data["currency"]
    doc = _Doc(lang, TEXT[lang]["expenses"], f"{period_label(data['start'], data['end'], lang)} · {cur}", user_name, password)
    t = doc.t
    prev = data["previous_total"]
    change = f"{(data['total'] - prev) / prev * 100:+.1f}%" if prev else "—"
    doc.tiles([
        (t["expense"], doc.money(data["total"], cur), RED, t["transactions"].format(n=data["count"])),
        (t["vs_previous"].format(amount="").rstrip(": "), doc.money(prev, cur), None, None),
        (t["change"], change, RED if prev and data["total"] > prev else GREEN if prev else None, None),
    ])
    if not data["categories"]:
        doc.text(t["no_data"], color=MUTED)
        return doc.output()

    palette = [BRAND, (14, 165, 233), (16, 185, 129), (245, 158, 11), (239, 68, 68), (139, 92, 246), (236, 72, 153), (100, 116, 139)]
    top_value = float(data["categories"][0]["amount"])
    doc.bar_rows([
        (_cat(lang, c["category"]), float(c["amount"]), f"{doc.money(c['amount'], cur)} · {c['share']:.0f}%", palette[i % len(palette)])
        for i, c in enumerate(data["categories"])
    ], top_value)

    doc.heading(t["by_category"])
    rows, colors = [], []
    for c in data["categories"]:
        ch = "—" if c["change"] is None else f"{c['change']:+.0f}%"
        rows.append([_cat(lang, c["category"]), str(c["count"]), doc.money(c["amount"], cur), f"{c['share']:.1f}%", doc.money(c["previous"], cur), ch])
        colors.append([None, MUTED, None, MUTED, MUTED, RED if (c["change"] or 0) > 0 else GREEN if c["change"] is not None else MUTED])
    doc.table(
        [(t["category"], 0.3, "L"), (t["count"], 0.08, "R"), (t["amount"], 0.18, "R"), (t["share"], 0.11, "R"),
         (t["vs_previous"].format(amount="").rstrip(": "), 0.19, "R"), (t["change"], 0.14, "R")],
        rows, colors,
    )

    doc.heading(t["top"])
    doc.table(
        [(t["date"], 0.15, "L"), (t["name"], 0.45, "L"), (t["category"], 0.22, "L"), (t["amount"], 0.18, "R")],
        [[_fmt_date(r["date"]), r["name"], _cat(lang, r["category"]), doc.money(r["amount"], cur)] for r in data["top"]],
    )
    doc.note(t["approx_fx"])
    return doc.output()


def render_budgets(data: dict, user_name: str, lang: Optional[str] = None, password: Optional[str] = None) -> bytes:
    lang = normalize_lang(lang)
    doc = _Doc(lang, TEXT[lang]["budgets"], period_label(data["start"], data["end"], lang), user_name, password)
    t = doc.t
    if not data["budgets"]:
        doc.text(t["no_budgets"], color=MUTED)
        return doc.output()

    for b in data["budgets"]:
        cur = b["currency"]
        doc.ensure(40)
        doc.heading(b["budget_name"])
        used = b["utilization_percent"]
        color = GREEN if used is None or used < 80 else AMBER if used <= 100 else RED
        remaining = b["remaining"]
        left_note = None
        if b["limit_amount"] is None:
            left_text, left_color = t["no_limit"], MUTED
        elif remaining is not None and remaining < 0:
            left_text, left_color, left_note = doc.money(remaining, cur), RED, t["over"]
        else:
            left_text, left_color = doc.money(remaining or 0, cur), None
        doc.tiles([
            (t["limit"], doc.money(b["limit_amount"], cur) if b["limit_amount"] is not None else t["no_limit"], None, None),
            (t["spent"], doc.money(b["actual_spent"], cur), None, None),
            (t["left"], left_text, left_color, left_note),
            (t["used"], f"{used:.0f}%" if used is not None else "—", color, None),
        ])
        if b["limit_amount"]:
            doc.bar_rows([(t["used"], float(b["actual_spent"]), f"{used:.0f}%", color)], float(b["limit_amount"]))
        if b["by_category"]:
            doc.table(
                [(t["category"], 0.6, "L"), (t["spent"], 0.4, "R")],
                [[_cat(lang, c["category"]), doc.money(c["amount"], cur)] for c in b["by_category"]],
            )
    doc.note(t["approx_fx"])
    return doc.output()


def render_recurring(data: dict, user_name: str, lang: Optional[str] = None, password: Optional[str] = None) -> bytes:
    lang = normalize_lang(lang)
    cur = data["currency"]
    doc = _Doc(lang, TEXT[lang]["recurring"], cur, user_name, password)
    t = doc.t
    share = data["income_share"]
    doc.tiles([
        (t["year_cost"], doc.money(data["expense_per_year"], cur), RED, t["month_cost"].format(amount=doc.money(data["expense_per_month"], cur))),
        (t["subs_year"], doc.money(data["subscriptions_per_year"], cur), AMBER, t["subs_note"].format(n=data["subscriptions_count"])),
        (t["income_share"], f"{share:.0f}%" if share is not None else "—", None, t["income_share_note"] if share is not None else None),
    ])
    if not data["expenses"] and not data["incomes"]:
        doc.text(t["no_recurring"], color=MUTED)
        return doc.output()
    if data["expense_per_year"]:
        doc.callout(t["callout"].format(year=doc.money(data["expense_per_year"], cur), month=doc.money(data["expense_per_month"], cur)))

    columns = [(t["name"], 0.27, "L"), (t["category"], 0.19, "L"), (t["frequency"], 0.15, "L"),
               (t["amount"], 0.13, "R"), (t["per_month"], 0.13, "R"), (t["per_year"], 0.13, "R")]

    def section(title, rows, total_month, total_year, color):
        if not rows:
            return
        doc.heading(title)
        body = [[r["name"], _cat(lang, r["category"]), t["freq"].get(r["frequency"], r["frequency"]),
                 doc.money(r["amount"], r["currency"]), doc.money(r["per_month"], cur), doc.money(r["per_year"], cur)]
                for r in rows]
        colors = [[None, MUTED, MUTED, MUTED, None, color] for _ in rows]
        body.append([t["total"], "", "", "", doc.money(total_month, cur), doc.money(total_year, cur)])
        colors.append([None, None, None, None, None, color])
        doc.table(columns, body, colors, bold_last=True)

    section(t["recurring_expenses"], data["expenses"], data["expense_per_month"], data["expense_per_year"], RED)
    income_month = sum((r["per_month"] for r in data["incomes"]), Decimal("0"))
    section(t["recurring_incomes"], data["incomes"], income_month, data["income_per_year"], GREEN)
    doc.note(t["approx_fx"])
    return doc.output()
