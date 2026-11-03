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
from app.models import CreditNote, CreditNoteItem, Invoice, InvoiceItem, ReturnRequest, User, UserRole
from app.schemas import CreditNoteResponse, PaginationParams

router = APIRouter()


async def generate_credit_note_number(db: AsyncSession, distributor_id: UUID) -> str:
    """Generate unique credit note number"""
    today = date.today()
    prefix = f"CN{today.strftime('%Y%m%d')}"
    
    result = await db.execute(
        select(func.count(CreditNote.id)).where(
            CreditNote.credit_note_number.like(f"{prefix}%")
        )
    )
    count = result.scalar() or 0
    return f"{prefix}{count + 1:05d}"


@router.post("/from-return/{return_request_id}", response_model=CreditNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_credit_note_from_return(
    return_request_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    """Create credit note from approved return request"""
    # Get return request with items
    return_result = await db.execute(
        select(ReturnRequest).options(
            joinedload(ReturnRequest.retailer),
            joinedload(ReturnRequest.invoice).joinedload(Invoice.distributor),
            selectinload(ReturnRequest.items).joinedload(ReturnRequestItem.invoice_item)
        ).where(ReturnRequest.id == return_request_id)
    )
    return_request = return_result.scalar_one_or_none()
    if not return_request:
        raise HTTPException(status_code=404, detail="Return request not found")
    
    if return_request.invoice.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if return_request.status != "approved":
        raise HTTPException(status_code=400, detail="Return request must be approved first")
    
    if return_request.credit_note_id:
        raise HTTPException(status_code=409, detail="Credit note already exists for this return")
    
    # Determine supply type
    from app.api.v1.endpoints.invoices import determine_supply_type
    supply_type = await determine_supply_type(
        return_request.invoice.distributor.gstin,
        return_request.retailer.gstin
    )
    
    # Create credit note items from approved return items
    cn_items = []
    taxable_value = Decimal("0")
    total_cgst = Decimal("0")
    total_sgst = Decimal("0")
    total_igst = Decimal("0")
    
    for rr_item in return_request.items:
        if rr_item.approved_quantity <= 0:
            continue
        
        invoice_item = rr_item.invoice_item
        qty = rr_item.approved_quantity
        unit_price = invoice_item.unit_price - invoice_item.discount
        item_taxable = unit_price * qty
        
        # Calculate GST
        from app.api.v1.endpoints.invoices import calculate_gst
        cgst, sgst, igst, item_tax = calculate_gst(item_taxable, invoice_item.gst_rate, supply_type)
        
        cn_items.append({
            "invoice_item_id": invoice_item.id,
            "product_name": invoice_item.product_name,
            "hsn_code": invoice_item.hsn_code,
            "batch_number": rr_item.batch_number,
            "expiry_date": rr_item.expiry_date,
            "quantity": qty,
            "unit_price": unit_price,
            "taxable_value": item_taxable,
            "gst_rate": invoice_item.gst_rate,
            "total_amount": item_taxable + item_tax,
        })
        
        taxable_value += item_taxable
        total_cgst += cgst
        total_sgst += sgst
        total_igst += igst
    
    total_tax = total_cgst + total_sgst + total_igst
    total_amount = taxable_value + total_tax
    
    # Create credit note
    credit_note = CreditNote(
        credit_note_number=await generate_credit_note_number(db, current_user.distributor_id),
        invoice_id=return_request.invoice_id,
        return_request_id=return_request_id,
        reason=return_request.reason_description or return_request.reason.value,
        taxable_value=taxable_value,
        cgst_amount=total_cgst,
        sgst_amount=total_sgst,
        igst_amount=total_igst,
        total_amount=total_amount,
        place_of_supply=return_request.retailer.state,
        supply_type=supply_type,
        status="issued",
        issued_at=datetime.utcnow(),
        issued_by=current_user.id,
    )
    db.add(credit_note)
    await db.flush()
    
    # Create credit note items
    for item_data in cn_items:
        cn_item = CreditNoteItem(
            credit_note_id=credit_note.id,
            **item_data
        )
        db.add(cn_item)
    
    # Update return request
    return_request.status = "credit_note_issued"
    return_request.credit_note_id = credit_note.id
    
    # Update retailer balance
    return_request.retailer.used_credit -= total_amount
    return_request.retailer.outstanding_balance -= total_amount
    
    # Update invoice payment status
    invoice = return_request.invoice
    invoice.balance_amount -= total_amount
    invoice.paid_amount += total_amount  # Credit note acts as payment
    
    if invoice.balance_amount <= 0:
        invoice.payment_status = PaymentStatus.PAID
    
    await db.commit()
    await db.refresh(credit_note)
    return await get_credit_note_with_details(credit_note.id, db)


async def get_credit_note_with_details(cn_id: UUID, db: AsyncSession) -> CreditNoteResponse:
    result = await db.execute(
        select(CreditNote).options(
            joinedload(CreditNote.invoice).joinedload(Invoice.retailer),
            joinedload(CreditNote.return_request),
            selectinload(CreditNote.items)
        ).where(CreditNote.id == cn_id)
    )
    return result.scalar_one()


@router.get("", response_model=List[CreditNoteResponse])
async def list_credit_notes(
    invoice_id: Optional[UUID] = None,
    retailer_id: Optional[UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    query = select(CreditNote).options(
        joinedload(CreditNote.invoice).joinedload(Invoice.retailer),
        joinedload(CreditNote.return_request),
        selectinload(CreditNote.items)
    ).join(Invoice).where(Invoice.distributor_id == current_user.distributor_id)
    
    if invoice_id:
        query = query.where(CreditNote.invoice_id == invoice_id)
    if retailer_id:
        query = query.join(Invoice).where(Invoice.retailer_id == retailer_id)
    if date_from:
        query = query.where(CreditNote.created_at >= date_from)
    if date_to:
        query = query.where(CreditNote.created_at <= date_to)
    
    query = query.order_by(CreditNote.created_at.desc())
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{cn_id}", response_model=CreditNoteResponse)
async def get_credit_note(
    cn_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    credit_note = await get_credit_note_with_details(cn_id, db)
    
    if credit_note.invoice.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return credit_note