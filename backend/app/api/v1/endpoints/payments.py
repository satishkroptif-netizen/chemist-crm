from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload, joinedload
from uuid import UUID
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime
from app.db.session import get_db
from app.core.security import get_current_active_user, require_distributor_access
from app.models import Payment, Invoice, PaymentStatus, User, UserRole
from app.schemas import PaymentCreate, PaymentResponse, PaymentListResponse, PaginationParams

router = APIRouter()


async def generate_payment_number(db: AsyncSession, distributor_id: UUID) -> str:
    """Generate unique payment number"""
    today = date.today()
    prefix = f"PAY{today.strftime('%Y%m%d')}"
    
    result = await db.execute(
        select(func.count(Payment.id)).where(
            Payment.payment_number.like(f"{prefix}%")
        )
    )
    count = result.scalar() or 0
    return f"{prefix}{count + 1:05d}"


@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    payment_data: PaymentCreate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    # Verify invoice belongs to distributor
    invoice_result = await db.execute(
        select(Invoice).options(
            joinedload(Invoice.retailer)
        ).where(Invoice.id == payment_data.invoice_id)
    )
    invoice = invoice_result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if invoice.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if invoice.payment_status == PaymentStatus.PAID:
        raise HTTPException(status_code=400, detail="Invoice already fully paid")
    
    if payment_data.amount > invoice.balance_amount:
        raise HTTPException(status_code=400, detail=f"Payment amount exceeds balance. Balance: {invoice.balance_amount}")
    
    payment = Payment(
        payment_number=await generate_payment_number(db, current_user.distributor_id),
        invoice_id=payment_data.invoice_id,
        amount=payment_data.amount,
        payment_mode=payment_data.payment_mode,
        reference_number=payment_data.reference_number,
        payment_date=payment_data.payment_date,
        notes=payment_data.notes,
        bank_name=payment_data.bank_name,
        cheque_date=payment_data.cheque_date,
        received_by=current_user.id,
    )
    db.add(payment)
    
    # Update invoice
    invoice.paid_amount += payment_data.amount
    invoice.balance_amount -= payment_data.amount
    
    if invoice.balance_amount <= 0:
        invoice.payment_status = PaymentStatus.PAID
        invoice.balance_amount = Decimal("0")
    elif invoice.paid_amount > 0:
        invoice.payment_status = PaymentStatus.PARTIAL
    
    # Update retailer balance
    invoice.retailer.used_credit -= payment_data.amount
    invoice.retailer.outstanding_balance -= payment_data.amount
    
    # Check for overdue
    if invoice.due_date < date.today() and invoice.balance_amount > 0:
        invoice.payment_status = PaymentStatus.OVERDUE
        invoice.retailer.overdue_days = (date.today() - invoice.due_date).days
        invoice.retailer.overdue_amount = invoice.balance_amount
    
    await db.commit()
    await db.refresh(payment)
    return payment


@router.get("", response_model=PaymentListResponse)
async def list_payments(
    pagination: PaginationParams = Depends(),
    invoice_id: Optional[UUID] = None,
    payment_mode: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    query = select(Payment).options(
        joinedload(Payment.invoice).joinedload(Invoice.retailer)
    ).join(Invoice).where(Invoice.distributor_id == current_user.distributor_id)
    
    if invoice_id:
        query = query.where(Payment.invoice_id == invoice_id)
    if payment_mode:
        query = query.where(Payment.payment_mode == payment_mode)
    if date_from:
        query = query.where(Payment.payment_date >= date_from)
    if date_to:
        query = query.where(Payment.payment_date <= date_to)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    query = query.offset((pagination.page - 1) * pagination.page_size).limit(pagination.page_size)
    query = query.order_by(Payment.payment_date.desc(), Payment.created_at.desc())
    
    result = await db.execute(query)
    payments = result.scalars().all()
    
    return PaymentListResponse(
        payments=payments,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Payment).options(
            joinedload(Payment.invoice).joinedload(Invoice.retailer)
        ).where(Payment.id == payment_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    if payment.invoice.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return payment


@router.patch("/{payment_id}/reconcile", response_model=PaymentResponse)
async def reconcile_payment(
    payment_id: UUID,
    clearance_date: Optional[date] = None,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Payment).options(joinedload(Payment.invoice))
        .where(Payment.id == payment_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    if payment.invoice.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    payment.is_reconciled = True
    payment.clearance_date = clearance_date or date.today()
    
    await db.commit()
    await db.refresh(payment)
    return payment


@router.delete("/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment(
    payment_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Payment).options(joinedload(Payment.invoice))
        .where(Payment.id == payment_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    if payment.invoice.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if payment.is_reconciled:
        raise HTTPException(status_code=400, detail="Cannot delete reconciled payment")
    
    # Reverse invoice
    invoice = payment.invoice
    invoice.paid_amount -= payment.amount
    invoice.balance_amount += payment.amount
    
    if invoice.balance_amount > 0 and invoice.paid_amount > 0:
        invoice.payment_status = PaymentStatus.PARTIAL
    elif invoice.balance_amount > 0:
        invoice.payment_status = PaymentStatus.PENDING
    else:
        invoice.payment_status = PaymentStatus.PAID
    
    # Update retailer
    invoice.retailer.used_credit += payment.amount
    invoice.retailer.outstanding_balance += payment.amount
    
    # Delete payment
    await db.delete(payment)
    await db.commit()