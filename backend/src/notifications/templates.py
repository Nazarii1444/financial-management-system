"""
E-mail texts (uk / en). Pure functions: data in → `Email` out, no DB, no network.

Every message has a plain-text and an HTML part with the same content. User-provided
values (names of budgets, goals, payments) are HTML-escaped. Amounts and category names
reuse the calendar export's formatting, so an e-mail shows "Оренда — 9 000 ₴" exactly like
the calendar event.
"""
from __future__ import annotations

from datetime import date, datetime
from html import escape
from typing import Iterable, List, Optional, Sequence, Tuple

from src.calendar_export.formatting import CATEGORY_NAMES, format_amount, normalize_lang
from src.notifications.mailer import Email

APP_NAME = "FinanceHub"

_MONTHS = {
    "uk": ["січень", "лютий", "березень", "квітень", "травень", "червень",
           "липень", "серпень", "вересень", "жовтень", "листопад", "грудень"],
    "en": ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"],
}

_COMMON = {
    "uk": {
        "hello": "Вітаємо, {name}!",
        "footer": "Ви отримали цей лист, бо користуєтеся {app}.",
        "manage": "Керувати сповіщеннями",
        "open": "Відкрити {app}",
    },
    "en": {
        "hello": "Hi {name},",
        "footer": "You are receiving this e-mail because you use {app}.",
        "manage": "Manage notifications",
        "open": "Open {app}",
    },
}


def _date(value: date, lang: str) -> str:
    return value.strftime("%d.%m.%Y") if lang == "uk" else value.strftime("%b %d, %Y").replace(" 0", " ")


def month_label(year: int, month: int, lang: str) -> str:
    return f"{_MONTHS[lang][month - 1]} {year}"


def _build(
    *,
    to: str,
    name: Optional[str],
    lang: str,
    subject: str,
    lines: Sequence[str],
    highlight: Optional[str] = None,
    table: Iterable[Tuple[str, str]] = (),
    frontend_url: str,
    link_path: str = "/",
    notification: bool = True,
) -> Email:
    """Shared layout: greeting, paragraphs, optional big highlighted value and a two-column table."""
    common = _COMMON[lang]
    table = list(table)
    hello = common["hello"].format(name=name or "")
    open_url = f"{frontend_url}{link_path}"
    settings_url = f"{frontend_url}/settings?tab=notifications"

    text_parts: List[str] = [hello, ""]
    text_parts += list(lines)
    if highlight:
        text_parts += ["", highlight]
    if table:
        text_parts.append("")
        text_parts += [f"{label}: {value}" for label, value in table]
    text_parts += ["", f"{common['open'].format(app=APP_NAME)}: {open_url}"]
    if notification:
        text_parts.append(f"{common['manage']}: {settings_url}")
    text_parts += ["", common["footer"].format(app=APP_NAME)]

    rows = "".join(
        f'<tr><td style="padding:6px 12px 6px 0;color:#6b7280">{escape(label)}</td>'
        f'<td style="padding:6px 0;font-weight:600;text-align:right">{escape(value)}</td></tr>'
        for label, value in table
    )
    html = f"""<!doctype html>
<html lang="{lang}"><body style="margin:0;padding:24px;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;color:#111827">
<div style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:12px;padding:28px">
<div style="font-size:20px;font-weight:700;color:#2563eb;margin-bottom:20px">{APP_NAME}</div>
<p style="margin:0 0 12px">{escape(hello)}</p>
{''.join(f'<p style="margin:0 0 12px;line-height:1.5">{escape(line)}</p>' for line in lines)}
{f'<div style="font-size:30px;font-weight:700;letter-spacing:4px;text-align:center;margin:20px 0;padding:14px;background:#eff6ff;border-radius:8px">{escape(highlight)}</div>' if highlight else ''}
{f'<table style="width:100%;border-collapse:collapse;margin:12px 0">{rows}</table>' if rows else ''}
<p style="margin:20px 0"><a href="{escape(open_url)}" style="background:#2563eb;color:#ffffff;text-decoration:none;padding:10px 18px;border-radius:8px;display:inline-block">{escape(common['open'].format(app=APP_NAME))}</a></p>
<hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0">
<p style="margin:0;font-size:12px;color:#6b7280">{escape(common['footer'].format(app=APP_NAME))}
{f'<br><a href="{escape(settings_url)}" style="color:#6b7280">{escape(common["manage"])}</a>' if notification else ''}</p>
</div></body></html>"""
    return Email(to=to, to_name=name, subject=subject, text="\n".join(text_parts), html=html)


# ── Account (always sent, not affected by notification preferences) ──────────

def password_reset_code(*, to: str, name: str, code: str, ttl_minutes: int, lang: str, frontend_url: str) -> Email:
    lang = normalize_lang(lang)
    if lang == "uk":
        subject = f"Код для відновлення пароля: {code}"
        lines = [
            "Ми отримали запит на відновлення пароля до вашого облікового запису.",
            f"Введіть цей код на сторінці відновлення. Він діє {ttl_minutes} хвилин і може бути використаний один раз.",
            "Якщо ви не запитували відновлення пароля, просто проігноруйте цей лист — ваш пароль не зміниться.",
        ]
    else:
        subject = f"Your password reset code: {code}"
        lines = [
            "We received a request to reset the password of your account.",
            f"Enter this code on the reset page. It is valid for {ttl_minutes} minutes and can be used once.",
            "If you didn't ask to reset your password, ignore this e-mail — your password stays the same.",
        ]
    return _build(to=to, name=name, lang=lang, subject=subject, lines=lines, highlight=code,
                  frontend_url=frontend_url, link_path="/forgot-password", notification=False)


def password_changed(*, to: str, name: str, when: datetime, lang: str, frontend_url: str) -> Email:
    lang = normalize_lang(lang)
    stamp = when.strftime("%d.%m.%Y %H:%M UTC") if lang == "uk" else when.strftime("%Y-%m-%d %H:%M UTC")
    if lang == "uk":
        subject = "Пароль до FinanceHub змінено"
        lines = [
            f"Пароль до вашого облікового запису було змінено через відновлення пароля ({stamp}).",
            "Якщо це були не ви, негайно відновіть пароль ще раз і перевірте історію входів у налаштуваннях безпеки.",
        ]
    else:
        subject = "Your FinanceHub password was changed"
        lines = [
            f"The password of your account was changed through a password reset ({stamp}).",
            "If this wasn't you, reset your password again right away and check the sign-in history in the security settings.",
        ]
    return _build(to=to, name=name, lang=lang, subject=subject, lines=lines,
                  frontend_url=frontend_url, link_path="/settings?tab=security", notification=False)


# ── Notifications (respect notification preferences) ─────────────────────────

def recurring_reminder(*, to: str, name: str, payment: str, amount, currency: str, category: str,
                       due: date, lang: str, frontend_url: str) -> Email:
    lang = normalize_lang(lang)
    money = format_amount(amount, currency, lang)
    category_name = CATEGORY_NAMES[lang].get(category, category)
    if lang == "uk":
        subject = f"Завтра платіж: {payment} — {money}"
        lines = [f"Нагадуємо: {_date(due, lang)} буде списано регулярний платіж «{payment}».",
                 "Переконайтеся, що на рахунку достатньо коштів."]
        table = [("Платіж", payment), ("Сума", money), ("Категорія", category_name), ("Дата", _date(due, lang))]
    else:
        subject = f"Payment tomorrow: {payment} — {money}"
        lines = [f"Reminder: the recurring payment “{payment}” is due on {_date(due, lang)}.",
                 "Make sure there is enough money on your account."]
        table = [("Payment", payment), ("Amount", money), ("Category", category_name), ("Date", _date(due, lang))]
    return _build(to=to, name=name, lang=lang, subject=subject, lines=lines, table=table,
                  frontend_url=frontend_url, link_path="/transactions")


def budget_alert(*, to: str, name: str, budget: str, percent: float, spent, limit, currency: str,
                 exceeded: bool, lang: str, frontend_url: str) -> Email:
    lang = normalize_lang(lang)
    spent_s, limit_s = format_amount(spent, currency, lang), format_amount(limit, currency, lang)
    pct = f"{percent:.0f} %" if lang == "uk" else f"{percent:.0f}%"
    if lang == "uk":
        if exceeded:
            subject = f"Бюджет «{budget}» перевищено"
            lines = [f"Витрати цього місяця перевищили ліміт бюджету «{budget}»."]
        else:
            subject = f"Бюджет «{budget}» використано на {pct}"
            lines = [f"Витрати цього місяця наближаються до ліміту бюджету «{budget}»."]
        lines.append("Перегляньте структуру витрат, щоб вчасно скоригувати плани.")
        table = [("Витрачено", spent_s), ("Ліміт", limit_s), ("Використано", pct)]
    else:
        if exceeded:
            subject = f"Budget “{budget}” exceeded"
            lines = [f"This month's spending went over the limit of the “{budget}” budget."]
        else:
            subject = f"Budget “{budget}” is {pct} used"
            lines = [f"This month's spending is getting close to the limit of the “{budget}” budget."]
        lines.append("Have a look at where the money goes to adjust your plans in time.")
        table = [("Spent", spent_s), ("Limit", limit_s), ("Used", pct)]
    return _build(to=to, name=name, lang=lang, subject=subject, lines=lines, table=table,
                  frontend_url=frontend_url, link_path="/budgets")


def goal_milestone(*, to: str, name: str, goal: str, milestone: int, saved, target, currency: str,
                   lang: str, frontend_url: str) -> Email:
    lang = normalize_lang(lang)
    saved_s, target_s = format_amount(saved, currency, lang), format_amount(target, currency, lang)
    if lang == "uk":
        if milestone >= 100:
            subject = f"Ціль «{goal}» досягнуто! 🎉"
            lines = [f"Вітаємо! Ви накопичили всю суму для цілі «{goal}»."]
        else:
            subject = f"Ціль «{goal}»: {milestone} % зібрано"
            lines = [f"Ви накопичили {milestone} % суми для цілі «{goal}». Так тримати!"]
        table = [("Накопичено", saved_s), ("Мета", target_s)]
    else:
        if milestone >= 100:
            subject = f"Goal “{goal}” reached! 🎉"
            lines = [f"Congratulations! You have saved the full amount for “{goal}”."]
        else:
            subject = f"Goal “{goal}”: {milestone}% saved"
            lines = [f"You have saved {milestone}% of the amount for “{goal}”. Keep it up!"]
        table = [("Saved", saved_s), ("Target", target_s)]
    return _build(to=to, name=name, lang=lang, subject=subject, lines=lines, table=table,
                  frontend_url=frontend_url, link_path="/goals")


def monthly_summary(*, to: str, name: str, year: int, month: int, income, expenses, net, currency: str,
                    top_categories: Sequence[Tuple[str, float]], lang: str, frontend_url: str) -> Email:
    lang = normalize_lang(lang)
    label = month_label(year, month, lang)
    money = lambda v: format_amount(v, currency, lang)  # noqa: E731
    sign = "+" if net >= 0 else "−"
    net_s = f"{sign}{money(abs(net))}"
    if lang == "uk":
        subject = f"Підсумок за {label}"
        lines = [f"Ось як минув {label}."]
        table = [("Доходи", money(income)), ("Витрати", money(expenses)), ("Різниця", net_s)]
        if top_categories:
            lines.append("Найбільші категорії витрат: " + ", ".join(
                f"{CATEGORY_NAMES['uk'].get(c, c)} ({money(a)})" for c, a in top_categories) + ".")
    else:
        subject = f"Your summary for {label}"
        lines = [f"Here is how {label} went."]
        table = [("Income", money(income)), ("Expenses", money(expenses)), ("Net", net_s)]
        if top_categories:
            lines.append("Top spending categories: " + ", ".join(
                f"{CATEGORY_NAMES['en'].get(c, c)} ({money(a)})" for c, a in top_categories) + ".")
    return _build(to=to, name=name, lang=lang, subject=subject, lines=lines, table=table,
                  frontend_url=frontend_url, link_path="/reports")
