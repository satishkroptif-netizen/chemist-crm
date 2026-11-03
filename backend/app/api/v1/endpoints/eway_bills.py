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
from app.models import EWayBill, Order, Invoice, Distributor, Retailer, User, UserRole
from app.schemas import EWayBillCreate, EWayBillResponse, PaginationParams

router = APIRouter()


@router.post("", response_model=EWayBillResponse, status_code=status.HTTP_201_CREATED)
async def create_eway_bill(
    eway_data: EWayBillCreate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    # Validate order or invoice
    if eway_data.order_id:
        order_result = await db.execute(
            select(Order).options(
                joinedload(Order.distributor),
                joinedload(Order.retailer)
            ).where(Order.id == eway_data.order_id)
        )
        order = order_result.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Check if e-way bill already exists
        existing = await db.execute(
            select(EWayBill).where(EWayBill.order_id == order.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="E-way bill already exists for this order")
        
        # Use invoice data if available
        invoice = order.invoices[0] if order.invoices else None
    
    elif eway_data.invoice_id:
        invoice_result = await db.execute(
            select(Invoice).options(
                joinedload(Invoice.distributor),
                joinedload(Invoice.retailer),
                joinedload(Invoice.order)
            ).where(Invoice.id == eway_data.invoice_id)
        )
        invoice = invoice_result.scalar_one_or_none()
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
        
        if invoice.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        order = invoice.order
        
        existing = await db.execute(
            select(EWayBill).where(EWayBill.invoice_id == invoice.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="E-way bill already exists for this invoice")
    
    else:
        raise HTTPException(status_code=400, detail="Either order_id or invoice_id must be provided")
    
    # Auto-fill from order/invoice if not provided
    if not eway_data.gstin_supplier:
        eway_data.gstin_supplier = invoice.distributor.gstin
    if not eway_data.gstin_recipient:
        eway_data.gstin_recipient = invoice.retailer.gstin
    if not eway_data.place_of_dispatch:
        eway_data.place_of_dispatch = f"{invoice.distributor.city}, {invoice.distributor.state}"
    if not eway_data.place_of_delivery:
        eway_data.place_of_delivery = f"{invoice.retailer.city}, {invoice.retailer.state}"
    if not eway_data.document_number:
        eway_data.document_number = invoice.invoice_number
    if not eway_data.document_date:
        eway_data.document_date = invoice.invoice_date
    if not eway_data.value_of_goods:
        eway_data.value_of_goods = invoice.total_amount
    
    # Get HSN codes from invoice items
    if not eway_data.hsn_codes:
        items_result = await db.execute(
            select(InvoiceItem.hsn_code).where(InvoiceItem.invoice_id == invoice.id).distinct()
        )
        eway_data.hsn_codes = [row[0] for row in items_result.all()]
    
    eway_bill = EWayBill(
        order_id=eway_data.order_id,
        invoice_id=eway_data.invoice_id,
        **eway_data.model_dump(exclude={"order_id", "invoice_id"}),
        status="draft",
    )
    db.add(eway_bill)
    await db.commit()
    await db.refresh(eway_bill)
    return eway_bill


@router.post("/{eway_bill_id}/generate", response_model=EWayBillResponse)
async def generate_eway_bill(
    eway_bill_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    """Generate e-way bill (integration with government portal would go here)"""
    result = await db.execute(
        select(EWayBill).where(EWayBill.id == eway_bill_id)
    )
    eway_bill = result.scalar_one_or_none()
    if not eway_bill:
        raise HTTPException(status_code=404, detail="E-way bill not found")
    
    # Verify access through order or invoice
    if eway_bill.order_id:
        order_result = await db.execute(
            select(Order).where(Order.id == eway_bill.order_id)
        )
        order = order_result.scalar_one()
        if order.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    elif eway_bill.invoice_id:
        invoice_result = await db.execute(
            select(Invoice).where(Invoice.id == eway_bill.invoice_id)
        )
        invoice = invoice_result.scalar_one()
        if invoice.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # In a real implementation, this would call the government e-way bill API
    # For now, we simulate generation
    eway_bill.status = "generated"
    eway_bill.eway_bill_number = f"EWB{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    eway_bill.eway_bill_date = datetime.utcnow()
    eway_bill.valid_upto = datetime.utcnow() + timedelta(days=1)  # 1 day validity for < 100km
    eway_bill.generated_by = current_user.id
    
    await db.commit()
    await db.refresh(eway_bill)
    return eway_bill


@router.post("/{eway_bill_id}/cancel", response_model=EWayBillResponse)
async def cancel_eway_bill(
    eway_bill_id: UUID,
    reason: str,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(EWayBill).where(EWayBill.id == eway_bill_id)
    )
    eway_bill = result.scalar_one_or_none()
    if not eway_bill:
        raise HTTPException(status_code=404, detail="E-way bill not found")
    
    # Verify access
    if eway_bill.order_id:
        order_result = await db.execute(select(Order).where(Order.id == eway_bill.order_id))
        order = order_result.scalar_one()
        if order.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    elif eway_bill.invoice_id:
        invoice_result = await db.execute(select(Invoice).where(Invoice.id == eway_bill.invoice_id))
        invoice = invoice_result.scalar_one()
        if invoice.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    if eway_bill.status == "cancelled":
        raise HTTPException(status_code=400, detail="E-way bill already cancelled")
    
    if eway_bill.status == "expired":
        raise HTTPException(status_code=400, detail="Cannot cancel expired e-way bill")
    
    eway_bill.status = "cancelled"
    eway_bill.cancelled_at = datetime.utcnow()
    eway_bill.cancelled_by = current_user.id
    eway_bill.cancellation_reason = reason
    
    await db.commit()
    await db.refresh(eway_bill)
    return eway_bill


@router.get("", response_model=List[EWayBillResponse])
async def list_eway_bills(
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    query = select(EWayBill).join(Order, EWayBill.order_id == Order.id, isouter=True).join(
        Invoice, EWayBill.invoice_id == Invoice.id, isouter=True
    ).where(
        or_(
            Order.distributor_id == current_user.distributor_id,
            Invoice.distributor_id == current_user.distributor_id
        )
    )
    
    if status:
        query = query.where(EWayBill.status == status)
    if date_from:
        query = query.where(EWayBill.eway_bill_date >= date_from)
    if date_to:
        query = query.where(EWayBill.eway_bill_date <= date_to)
    
    query = query.order_by(EWayBill.created_at.desc())
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{eway_bill_id}", response_model=EWayBillResponse)
async def get_eway_bill(
    eway_bill_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(EWayBill).where(EWayBill.id == eway_bill_id)
    )
    eway_bill = result.scalar_one_or_none()
    if not eway_bill:
        raise HTTPException(status_code=404, detail="E-way bill not found")
    
    # Verify access
    if eway_bill.order_id:
        order_result = await db.execute(select(Order).where(Order.id == eway_bill.order_id))
        order = order_result.scalar_one()
        if order.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    elif eway_bill.invoice_id:
        invoice_result = await db.execute(select(Invoice).where(Invoice.id == eway_bill.invoice_id))
        invoice = invoice_result.scalar_one()
        if invoice.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return eway_bill