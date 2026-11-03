from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload, joinedload
from uuid import UUID
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime, timedelta
from app.db.session import get_db
from app.core.security import get_current_active_user, require_distributor_access
from app.models import (
    Invoice, InvoiceItem, InvoiceStatus, PaymentStatus,
    Order, OrderItem, OrderStatus, Retailer, Distributor,
    Product, User, UserRole
)
from app.schemas import InvoiceGenerateRequest, InvoiceResponse, InvoiceListResponse, PaginationParams

router = APIRouter()


async def generate_invoice_number(db: AsyncSession, distributor_id: UUID, series: str) -> str:
    """Generate unique invoice number"""
    today = date.today()
    prefix = f"INV{series}{today.strftime('%Y%m%d')}"
    
    result = await db.execute(
        select(func.count(Invoice.id)).where(
            Invoice.distributor_id == distributor_id,
            Invoice.invoice_series == series,
            Invoice.invoice_number.like(f"{prefix}%")
        )
    )
    count = result.scalar() or 0
    return f"{prefix}{count + 1:05d}"


def calculate_gst(amount: Decimal, gst_rate: Decimal, supply_type: str) -> tuple:
    """Calculate CGST, SGST, IGST based on supply type"""
    total_tax = amount * gst_rate / 100
    if supply_type == "intra_state":
        cgst = total_tax / 2
        sgst = total_tax / 2
        igst = Decimal("0")
    else:  # inter_state
        cgst = Decimal("0")
        sgst = Decimal("0")
        igst = total_tax
    return cgst, sgst, igst, total_tax


async def determine_supply_type(distributor_gstin: str, retailer_gstin: str) -> str:
    """Determine if supply is intra-state or inter-state based on GSTIN state codes"""
    distributor_state = distributor_gstin[:2]
    retailer_state = retailer_gstin[:2]
    return "intra_state" if distributor_state == retailer_state else "inter_state"


@router.post("/generate", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def generate_invoice(
    request: InvoiceGenerateRequest,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    # Get order with details
    order_result = await db.execute(
        select(Order).options(
            joinedload(Order.retailer),
            joinedload(Order.distributor),
            selectinload(Order.items).joinedload(OrderItem.product),
            selectinload(Order.items).joinedload(OrderItem.batch)
        ).where(Order.id == request.order_id)
    )
    order = order_result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if order.status != OrderStatus.APPROVED_BY_CREDIT:
        raise HTTPException(status_code=400, detail="Order must be approved by credit before invoicing")
    
    # Check if already invoiced
    existing_invoice = await db.execute(
        select(Invoice).where(Invoice.order_id == order.id)
    )
    if existing_invoice.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Order already invoiced")
    
    # Determine supply type
    supply_type = await determine_supply_type(order.distributor.gstin, order.retailer.gstin)
    
    invoice_date = request.invoice_date or date.today()
    due_date = request.due_date or (invoice_date + timedelta(days=order.retailer.payment_terms_days))
    
    # Create invoice items from order items
    invoice_items = []
    taxable_value = Decimal("0")
    total_cgst = Decimal("0")
    total_sgst = Decimal("0")
    total_igst = Decimal("0")
    
    for order_item in order.items:
        # Calculate taxes
        cgst, sgst, igst, item_tax = calculate_gst(
            order_item.line_subtotal,
            order_item.gst_rate,
            supply_type
        )
        
        invoice_items.append({
            "order_item_id": order_item.id,
            "product_name": order_item.product_name,
            "product_sku": order_item.product_sku,
            "hsn_code": order_item.hsn_code,
            "batch_number": order_item.batch_number,
            "expiry_date": order_item.expiry_date,
            "unit_of_measure": order_item.unit_of_measure,
            "pack_size": order_item.pack_size,
            "quantity": order_item.ordered_qty,
            "unit_price": order_item.unit_price,
            "discount": order_item.discount_per_unit,
            "taxable_value": order_item.line_subtotal,
            "gst_rate": order_item.gst_rate,
            "cgst_rate": order_item.gst_rate / 2 if supply_type == "intra_state" else Decimal("0"),
            "sgst_rate": order_item.gst_rate / 2 if supply_type == "intra_state" else Decimal("0"),
            "igst_rate": order_item.gst_rate if supply_type == "inter_state" else Decimal("0"),
            "cgst_amount": cgst,
            "sgst_amount": sgst,
            "igst_amount": igst,
            "total_amount": order_item.line_subtotal + item_tax,
        })
        
        taxable_value += order_item.line_subtotal
        total_cgst += cgst
        total_sgst += sgst
        total_igst += igst
    
    total_tax = total_cgst + total_sgst + total_igst
    total_amount = taxable_value + total_tax
    round_off = round(total_amount) - total_amount
    total_amount = round(total_amount)
    
    # Create invoice
    invoice = Invoice(
        invoice_number=await generate_invoice_number(db, order.distributor_id, request.invoice_series),
        invoice_series=request.invoice_series,
        status=InvoiceStatus.GENERATED,
        distributor_id=order.distributor_id,
        retailer_id=order.retailer_id,
        order_id=order.id,
        taxable_value=taxable_value,
        cgst_amount=total_cgst,
        sgst_amount=total_sgst,
        igst_amount=total_igst,
        total_tax=total_tax,
        total_amount=total_amount,
        round_off=round_off,
        place_of_supply=order.retailer.state,
        supply_type=supply_type,
        reverse_charge=False,
        invoice_date=invoice_date,
        due_date=due_date,
        generated_at=datetime.utcnow(),
        payment_status=PaymentStatus.PENDING,
        paid_amount=Decimal("0"),
        balance_amount=total_amount,
    )
    db.add(invoice)
    await db.flush()
    
    # Create invoice items
    for item_data in invoice_items:
        invoice_item = InvoiceItem(
            invoice_id=invoice.id,
            **item_data
        )
        db.add(invoice_item)
    
    # Update order status
    order.status = OrderStatus.INVOICED
    order.invoiced_at = datetime.utcnow()
    
    # Update retailer credit
    order.retailer.used_credit += total_amount
    order.retailer.outstanding_balance += total_amount
    
    # Create status history
    from app.models import OrderStatusHistory
    status_history = OrderStatusHistory(
        order_id=order.id,
        from_status=OrderStatus.APPROVED_BY_CREDIT,
        to_status=OrderStatus.INVOICED,
        changed_by=current_user.id,
        notes="Invoice generated"
    )
    db.add(status_history)
    
    await db.commit()
    await db.refresh(invoice)
    return await get_invoice_with_details(invoice.id, db)


async def get_invoice_with_details(invoice_id: UUID, db: AsyncSession) -> InvoiceResponse:
    result = await db.execute(
        select(Invoice).options(
            joinedload(Invoice.retailer),
            joinedload(Invoice.distributor),
            joinedload(Invoice.order).joinedload(Order.warehouse),
            joinedload(Invoice.order).selectinload(Order.items),
            joinedload(Invoice.order).selectinload(Order.status_history),
            selectinload(Invoice.items)
        ).where(Invoice.id == invoice_id)
    )
    return result.scalar_one()


@router.get("", response_model=InvoiceListResponse)
async def list_invoices(
    pagination: PaginationParams = Depends(),
    status: Optional[InvoiceStatus] = None,
    retailer_id: Optional[UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    payment_status: Optional[PaymentStatus] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Invoice).options(
        joinedload(Invoice.retailer),
        joinedload(Invoice.distributor),
        joinedload(Invoice.order).joinedload(Order.warehouse),
        joinedload(Invoice.order).selectinload(Order.items),
        joinedload(Invoice.order).selectinload(Order.status_history),
        selectinload(Invoice.items)
    )
    
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        query = query.where(Invoice.retailer_id == current_user.retailer_id)
    else:
        query = query.where(Invoice.distributor_id == current_user.distributor_id)
        if retailer_id:
            query = query.where(Invoice.retailer_id == retailer_id)
    
    if status:
        query = query.where(Invoice.status == status)
    if payment_status:
        query = query.where(Invoice.payment_status == payment_status)
    if date_from:
        query = query.where(Invoice.invoice_date >= date_from)
    if date_to:
        query = query.where(Invoice.invoice_date <= date_to)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    query = query.offset((pagination.page - 1) * pagination.page_size).limit(pagination.page_size)
    query = query.order_by(Invoice.created_at.desc())
    
    result = await db.execute(query)
    invoices = result.scalars().all()
    
    return InvoiceListResponse(
        invoices=invoices,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    invoice = await get_invoice_with_details(invoice_id, db)
    
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        if invoice.retailer_id != current_user.retailer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if invoice.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return invoice


@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    invoice_id: UUID,
    reason: str,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    invoice = await get_invoice_with_details(invoice_id, db)
    
    if invoice.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if invoice.status == InvoiceStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Invoice already cancelled")
    
    if invoice.status == InvoiceStatus.E_INVOICE_GENERATED:
        raise HTTPException(status_code=400, detail="Cannot cancel e-invoice generated invoice")
    
    # Reverse retailer credit
    invoice.retailer.used_credit -= invoice.total_amount
    invoice.retailer.outstanding_balance -= invoice.total_amount
    
    # Update order status back
    invoice.order.status = OrderStatus.APPROVED_BY_CREDIT
    invoice.order.invoiced_at = None
    
    invoice.status = InvoiceStatus.CANCELLED
    
    await db.commit()
    return await get_invoice_with_details(invoice_id, db)


@router.get("/{invoice_id}/download")
async def download_invoice(
    invoice_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Generate invoice PDF/download data"""
    invoice = await get_invoice_with_details(invoice_id, db)
    
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        if invoice.retailer_id != current_user.retailer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if invoice.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Return structured data for PDF generation
    return {
        "invoice": invoice,
        "distributor": invoice.distributor,
        "retailer": invoice.retailer,
        "items": invoice.items,
        "generated_at": datetime.utcnow().isoformat(),
    }