from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, case
from sqlalchemy.orm import selectinload, joinedload
from uuid import UUID
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime, timedelta
from app.db.session import get_db
from app.core.security import get_current_active_user, require_distributor_access, require_retailer_access
from app.models import LedgerEntry, Invoice, Payment, CreditNote, Retailer, User, UserRole, Order, OrderStatus
from app.schemas import LedgerEntryResponse, LedgerSummaryResponse, PaginationParams

router = APIRouter()


@router.get("/retailer/{retailer_id}", response_model=LedgerSummaryResponse)
async def get_retailer_ledger(
    retailer_id: UUID,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    entry_type: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify access
    retailer_result = await db.execute(select(Retailer).where(Retailer.id == retailer_id))
    retailer = retailer_result.scalar_one_or_none()
    if not retailer:
        raise HTTPException(status_code=404, detail="Retailer not found")
    
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        if retailer_id != current_user.retailer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if retailer.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Get ledger entries
    query = select(LedgerEntry).where(LedgerEntry.retailer_id == retailer_id)
    
    if date_from:
        query = query.where(LedgerEntry.entry_date >= date_from)
    if date_to:
        query = query.where(LedgerEntry.entry_date <= date_to)
    if entry_type:
        query = query.where(LedgerEntry.entry_type == entry_type)
    
    query = query.order_by(LedgerEntry.entry_date, LedgerEntry.created_at)
    
    result = await db.execute(query)
    entries = result.scalars().all()
    
    # Calculate summary
    opening_balance = Decimal("0")
    total_invoices = Decimal("0")
    total_payments = Decimal("0")
    total_credit_notes = Decimal("0")
    
    for entry in entries:
        if entry.entry_type == "invoice":
            total_invoices += entry.debit_amount
        elif entry.entry_type == "payment":
            total_payments += entry.credit_amount
        elif entry.entry_type == "credit_note":
            total_credit_notes += entry.credit_amount
    
    closing_balance = opening_balance + total_invoices - total_payments - total_credit_notes
    available_credit = retailer.credit_limit - closing_balance
    
    # Calculate overdue
    overdue_query = select(func.sum(Invoice.balance_amount)).where(
        Invoice.retailer_id == retailer_id,
        Invoice.payment_status.in_(["pending", "partial", "overdue"]),
        Invoice.due_date < date.today()
    )
    overdue_amount = await db.scalar(overdue_query) or Decimal("0")
    
    overdue_days = 0
    if overdue_amount > 0:
        oldest_overdue = await db.scalar(
            select(func.min(Invoice.due_date)).where(
                Invoice.retailer_id == retailer_id,
                Invoice.payment_status.in_(["pending", "partial", "overdue"]),
                Invoice.due_date < date.today()
            )
        )
        if oldest_overdue:
            overdue_days = (date.today() - oldest_overdue).days
    
    return LedgerSummaryResponse(
        retailer_id=retailer.id,
        retailer_name=retailer.name,
        opening_balance=opening_balance,
        total_invoices=total_invoices,
        total_payments=total_payments,
        total_credit_notes=total_credit_notes,
        closing_balance=closing_balance,
        credit_limit=retailer.credit_limit,
        available_credit=max(available_credit, Decimal("0")),
        overdue_amount=overdue_amount,
        overdue_days=overdue_days,
        entries=entries
    )


@router.get("/retailer/{retailer_id}/entries", response_model=List[LedgerEntryResponse])
async def get_ledger_entries(
    retailer_id: UUID,
    pagination: PaginationParams = Depends(),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    entry_type: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    retailer_result = await db.execute(select(Retailer).where(Retailer.id == retailer_id))
    retailer = retailer_result.scalar_one_or_none()
    if not retailer:
        raise HTTPException(status_code=404, detail="Retailer not found")
    
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        if retailer_id != current_user.retailer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if retailer.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    query = select(LedgerEntry).where(LedgerEntry.retailer_id == retailer_id)
    
    if date_from:
        query = query.where(LedgerEntry.entry_date >= date_from)
    if date_to:
        query = query.where(LedgerEntry.entry_date <= date_to)
    if entry_type:
        query = query.where(LedgerEntry.entry_type == entry_type)
    
    query = query.order_by(LedgerEntry.entry_date.desc(), LedgerEntry.created_at.desc())
    
    # Apply pagination
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    query = query.offset((pagination.page - 1) * pagination.page_size).limit(pagination.page_size)
    
    result = await db.execute(query)
    entries = result.scalars().all()
    
    return entries


@router.post("/retailer/{retailer_id}/recompute", status_code=status.HTTP_200_OK)
async def recompute_ledger(
    retailer_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    """Recompute ledger entries from invoices, payments, credit notes"""
    retailer_result = await db.execute(select(Retailer).where(Retailer.id == retailer_id))
    retailer = retailer_result.scalar_one_or_none()
    if not retailer:
        raise HTTPException(status_code=404, detail="Retailer not found")
    
    if retailer.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Delete existing ledger entries
    await db.execute(
        select(LedgerEntry).where(LedgerEntry.retailer_id == retailer_id).delete()
    )
    
    # Get all invoices
    invoices_result = await db.execute(
        select(Invoice).where(Invoice.retailer_id == retailer_id).order_by(Invoice.invoice_date)
    )
    invoices = invoices_result.scalars().all()
    
    # Get all payments
    payments_result = await db.execute(
        select(Payment).join(Invoice).where(Invoice.retailer_id == retailer_id).order_by(Payment.payment_date)
    )
    payments = payments_result.scalars().all()
    
    # Get all credit notes
    cn_result = await db.execute(
        select(CreditNote).join(Invoice).where(Invoice.retailer_id == retailer_id).order_by(CreditNote.created_at)
    )
    credit_notes = cn_result.scalars().all()
    
    # Combine and sort by date
    all_transactions = []
    for inv in invoices:
        all_transactions.append(("invoice", inv.invoice_date, inv.id, inv.total_amount, f"Invoice {inv.invoice_number}"))
    for pay in payments:
        all_transactions.append(("payment", pay.payment_date, pay.id, pay.amount, f"Payment {pay.payment_number}"))
    for cn in credit_notes:
        all_transactions.append(("credit_note", cn.created_at.date(), cn.id, cn.total_amount, f"Credit Note {cn.credit_note_number}"))
    
    all_transactions.sort(key=lambda x: x[1])
    
    # Create ledger entries
    balance = Decimal("0")
    for txn_type, txn_date, txn_id, amount, desc in all_transactions:
        if txn_type == "invoice":
            entry = LedgerEntry(
                retailer_id=retailer_id,
                invoice_id=txn_id,
                entry_type="invoice",
                description=desc,
                debit_amount=amount,
                credit_amount=Decimal("0"),
                balance=balance + amount,
                entry_date=txn_date,
                reference_number=txn_id,
            )
            balance += amount
        elif txn_type == "payment":
            entry = LedgerEntry(
                retailer_id=retailer_id,
                payment_id=txn_id,
                entry_type="payment",
                description=desc,
                debit_amount=Decimal("0"),
                credit_amount=amount,
                balance=balance - amount,
                entry_date=txn_date,
                reference_number=txn_id,
            )
            balance -= amount
        elif txn_type == "credit_note":
            entry = LedgerEntry(
                retailer_id=retailer_id,
                credit_note_id=txn_id,
                entry_type="credit_note",
                description=desc,
                debit_amount=Decimal("0"),
                credit_amount=amount,
                balance=balance - amount,
                entry_date=txn_date,
                reference_number=txn_id,
            )
            balance -= amount
        
        db.add(entry)
    
    # Update retailer balance
    retailer.outstanding_balance = balance
    retailer.used_credit = balance
    
    await db.commit()
    
    return {"message": "Ledger recomputed successfully", "entries_created": len(all_transactions), "closing_balance": float(balance)}