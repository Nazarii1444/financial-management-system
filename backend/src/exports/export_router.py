"""
Exports: transactions as CSV (same filters as search) and PDF reports.

    GET /transactions.csv            ?q=…&date_from=…&lang=uk|en (all /transactions/search filters)
    GET /reports/statement.pdf       ?month=YYYY-MM
    GET /reports/expenses.pdf        ?month=YYYY-MM or ?date_from&date_to (default: current month)
    GET /reports/budgets.pdf         ?month=YYYY-MM
    GET /reports/recurring.pdf
    GET /reports/recurring           JSON — monthly / yearly cost of recurring rules

Optional `X-Export-Passphrase` header, percent-encoded UTF-8 (`encodeURIComponent`
— headers are Latin-1, passphrases may be Cyrillic; a header, so it never lands
in URLs or access logs): PDFs get standard AES-256 password protection, the CSV becomes an
encrypted `.csv.fhx` that `POST /api/transactions/import/statement/preview`
opens with the same passphrase.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from src.calendar_export.formatting import normalize_lang
from src.database import get_db
from src.dependencies import get_current_user
from src.exports import crypto, pdf, reports
from src.exports.csv_export import transactions_csv
from src.exports.schemas import RecurringSummaryOut
from src.models import User
from src.security.events import EventType, record_event
from src.transactions.services.search_service import SearchFilters, search_transactions
from src.transactions.transaction_router import search_filters

export_router = APIRouter()


def _file(content: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


async def _logged(session: AsyncSession, user: User, request: Request, passphrase: Optional[str], response: Response) -> Response:
    """Record the download in the user's security history, then return it."""
    filename = response.headers["Content-Disposition"].split('filename="')[1].rstrip('"')
    await record_event(session, user.id_, EventType.DATA_EXPORTED, request,
                       details={"file": filename, "encrypted": bool(passphrase)})
    return response


def export_passphrase(
    x_export_passphrase: Optional[str] = Header(None, description="Encrypt the file with this passphrase (percent-encoded UTF-8)"),
) -> Optional[str]:
    if not x_export_passphrase:
        return None
    try:
        return crypto.validate_passphrase(unquote(x_export_passphrase, errors="strict"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _month(month: Optional[str]) -> str:
    month = month or reports.current_month()
    try:
        reports.month_bounds(month)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return month


def _render(render, data, user: User, lang: Optional[str], password: Optional[str] = None) -> bytes:
    try:
        return render(data, user.username, lang, password)
    except pdf.PdfUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc))


@export_router.get("/transactions.csv", response_class=Response, summary="Transactions as CSV (Excel-friendly)")
async def export_csv(
    request: Request,
    filters: SearchFilters = Depends(search_filters),
    lang: Optional[str] = Query(None, description="uk → ';' + decimal comma, en → ',' + decimal point"),
    passphrase: Optional[str] = Depends(export_passphrase),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    hits = await search_transactions(session, current_user, filters)
    body = transactions_csv(hits, lang).encode("utf-8")
    filename = f"financehub-transactions-{datetime.now(timezone.utc):%Y-%m-%d}.csv"
    if passphrase:
        # scrypt is ~0.1 s of CPU — keep it off the event loop
        body = await run_in_threadpool(crypto.encrypt, body, passphrase)
        return await _logged(session, current_user, request, passphrase, _file(
            body, "application/octet-stream", filename + crypto.EXTENSION))
    return await _logged(session, current_user, request, passphrase, _file(
        body, "text/csv; charset=utf-8", filename))


@export_router.get("/reports/statement.pdf", response_class=Response, summary="Monthly statement")
async def statement_pdf(
    request: Request,
    month: Optional[str] = Query(None, description="YYYY-MM, default: current month"),
    lang: Optional[str] = Query(None),
    passphrase: Optional[str] = Depends(export_passphrase),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    month = _month(month)
    data = await reports.statement(session, current_user, month)
    return await _logged(session, current_user, request, passphrase, _file(
        _render(pdf.render_statement, data, current_user, lang, passphrase), "application/pdf", f"statement-{month}.pdf"))


@export_router.get("/reports/expenses.pdf", response_class=Response, summary="Expense structure by category")
async def expenses_pdf(
    request: Request,
    month: Optional[str] = Query(None, description="YYYY-MM; takes precedence over date_from / date_to"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    lang: Optional[str] = Query(None),
    passphrase: Optional[str] = Depends(export_passphrase),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if month or date_from is None or date_to is None:
        start, end = reports.month_bounds(_month(month))
    else:
        start = date_from if date_from.tzinfo else date_from.replace(tzinfo=timezone.utc)
        end = (date_to if date_to.tzinfo else date_to.replace(tzinfo=timezone.utc)) + timedelta(microseconds=1)
        if end <= start:
            raise HTTPException(status_code=422, detail="date_to must be after date_from")
    data = await reports.expense_structure(session, current_user, start, end)
    return await _logged(session, current_user, request, passphrase, _file(
        _render(pdf.render_expenses, data, current_user, lang, passphrase), "application/pdf",
                 f"expenses-{start:%Y-%m-%d}.pdf"))


@export_router.get("/reports/budgets.pdf", response_class=Response, summary="Budget plan performance")
async def budgets_pdf(
    request: Request,
    month: Optional[str] = Query(None),
    lang: Optional[str] = Query(None),
    passphrase: Optional[str] = Depends(export_passphrase),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    month = _month(month)
    data = await reports.budget_plans(session, current_user, month)
    return await _logged(session, current_user, request, passphrase, _file(
        _render(pdf.render_budgets, data, current_user, lang, passphrase), "application/pdf", f"budgets-{month}.pdf"))


@export_router.get("/reports/recurring.pdf", response_class=Response, summary="Recurring payments: monthly / yearly cost")
async def recurring_pdf(
    request: Request,
    lang: Optional[str] = Query(None),
    passphrase: Optional[str] = Depends(export_passphrase),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await reports.recurring_summary(session, current_user)
    return await _logged(session, current_user, request, passphrase, _file(
        _render(pdf.render_recurring, data, current_user, normalize_lang(lang), passphrase), "application/pdf",
                 "recurring-payments.pdf"))


@export_router.get("/reports/recurring", response_model=RecurringSummaryOut, summary="Recurring payments cost (JSON)")
async def recurring_json(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await reports.recurring_summary(session, current_user)
