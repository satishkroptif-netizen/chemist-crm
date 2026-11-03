from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload, joinedload
from uuid import UUID
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime
from app.db.session import get_db
from app.core.security import get_current_active_user, require_distributor_access, require_retailer_access
from app.models import (
    ReturnRequest, ReturnRequestItem, ReturnReason,
    Invoice, InvoiceItem, Order, OrderItem, Retailer, ProductBatch, Inventory,
    User, UserRole
)
from app.schemas import ReturnRequestCreate, ReturnRequestProcessRequest, ReturnRequestInspectionRequest, ReturnRequestResponse, ReturnRequestListResponse, PaginationParams

router = APIRouter()


async def generate_return_number(db: AsyncSession, distributor_id: UUID) -> str:
    """Generate unique return number"""
    today = date.today()
    prefix = f"RET{today.strftime('%Y%m%d')}"
    
    result = await db.execute(
        select(func.count(ReturnRequest.id)).where(
            ReturnRequest.return_number.like(f"{prefix}%")
        )
    )
    count = result.scalar() or 0
    return f"{prefix}{count + 1:05d}"


@router.post("", response_model=ReturnRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_return_request(
    return_data: ReturnRequestCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify invoice
    invoice_result = await db.execute(
        select(Invoice).options(joinedload(Invoice.retailer))
        .where(Invoice.id == return_data.invoice_id)
    )
    invoice = invoice_result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    # Check access
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        if invoice.retailer_id != current_user.retailer_id:
            raise HTTPException(status_code=403, detail="Access denied")
        retailer_id = current_user.retailer_id
    else:
        if invoice.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
        retailer_id = invoice.retailer_id
    
    # Check invoice is delivered
    if invoice.order.status != "delivered" and invoice.order.status != "closed":
        raise HTTPException(status_code=400, detail="Can only return delivered orders")
    
    # Validate items
    invoice_item_ids = [item.invoice_item_id for item in return_data.items]
    invoice_items_result = await db.execute(
        select(InvoiceItem).where(InvoiceItem.id.in_(invoice_item_ids))
    )
    invoice_items = {item.id: item for item in invoice_items_result.scalars().all()}
    
    if len(invoice_items) != len(invoice_item_ids):
        raise HTTPException(status_code=400, detail="One or more invoice items not found")
    
    # Check quantities don't exceed delivered
    for item_data in return_data.items:
        invoice_item = invoice_items[item_data.invoice_item_id]
        delivered_qty = invoice_item.quantity  # Assuming invoice quantity = delivered
        if item_data.quantity > delivered_qty:
            raise HTTPException(
                status_code=400,
                detail=f"Return quantity exceeds delivered quantity for {invoice_item.product_name}"
            )
    
    # Check for existing return requests
    existing_result = await db.execute(
        select(ReturnRequestItem).join(ReturnRequest).where(
            ReturnRequest.invoice_id == return_data.invoice_id,
            ReturnRequestItem.invoice_item_id.in_(invoice_item_ids),
            ReturnRequest.status.in_(["pending", "approved", "received"])
        )
    )
    existing = existing_result.scalars().all()
    if existing:
        raise HTTPException(status_code=409, detail="Return already requested for some items")
    
    # Create return request
    return_request = ReturnRequest(
        return_number=await generate_return_number(db, invoice.distributor_id),
        retailer_id=retailer_id,
        invoice_id=return_data.invoice_id,
        order_id=invoice.order_id,
        reason=return_data.reason,
        reason_description=return_data.reason_description,
        status="pending",
        requested_by=current_user.id,
        requires_inspection=return_data.reason in [ReturnReason.BREAKAGE, ReturnReason.QUALITY_ISSUE],
    )
    db.add(return_request)
    await db.flush()
    
    # Create return request items
    for item_data in return_data.items:
        invoice_item = invoice_items[item_data.invoice_item_id]
        
        rr_item = ReturnRequestItem(
            return_request_id=return_request.id,
            invoice_item_id=item_data.invoice_item_id,
            product_name=invoice_item.product_name,
            batch_number=invoice_item.batch_number,
            expiry_date=invoice_item.expiry_date,
            quantity=item_data.quantity,
            unit_price=invoice_item.unit_price,
            total_amount=invoice_item.unit_price * item_data.quantity,
        )
        db.add(rr_item)
    
    await db.commit()
    await db.refresh(return_request)
    return await get_return_with_details(return_request.id, db)


async def get_return_with_details(return_id: UUID, db: AsyncSession) -> ReturnRequestResponse:
    result = await db.execute(
        select(ReturnRequest).options(
            joinedload(ReturnRequest.retailer),
            joinedload(ReturnRequest.invoice).joinedload(Invoice.distributor),
            joinedload(ReturnRequest.order),
            joinedload(ReturnRequest.credit_note),
            selectinload(ReturnRequest.items)
        ).where(ReturnRequest.id == return_id)
    )
    return result.scalar_one()


@router.get("", response_model=ReturnRequestListResponse)
async def list_return_requests(
    pagination: PaginationParams = Depends(),
    status: Optional[str] = None,
    retailer_id: Optional[UUID] = None,
    reason: Optional[ReturnReason] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(ReturnRequest).options(
        joinedload(ReturnRequest.retailer),
        joinedload(ReturnRequest.invoice).joinedload(Invoice.distributor),
        joinedload(ReturnRequest.credit_note),
        selectinload(ReturnRequest.items)
    )
    
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        query = query.where(ReturnRequest.retailer_id == current_user.retailer_id)
    else:
        query = query.join(Invoice).where(Invoice.distributor_id == current_user.distributor_id)
        if retailer_id:
            query = query.where(ReturnRequest.retailer_id == retailer_id)
    
    if status:
        query = query.where(ReturnRequest.status == status)
    if reason:
        query = query.where(ReturnRequest.reason == reason)
    if date_from:
        query = query.where(ReturnRequest.requested_at >= date_from)
    if date_to:
        query = query.where(ReturnRequest.requested_at <= date_to)
    
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    query = query.offset((pagination.page - 1) * pagination.page_size).limit(pagination.page_size)
    query = query.order_by(ReturnRequest.requested_at.desc())
    
    result = await db.execute(query)
    returns = result.scalars().all()
    
    return ReturnRequestListResponse(
        returns=returns,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size
    )


@router.get("/{return_id}", response_model=ReturnRequestResponse)
async def get_return_request(
    return_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    return_request = await get_return_with_details(return_id, db)
    
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        if return_request.retailer_id != current_user.retailer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if return_request.invoice.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return return_request


@router.post("/{return_id}/process", response_model=ReturnRequestResponse)
async def process_return_request(
    return_id: UUID,
    process_data: ReturnRequestProcessRequest,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    return_request = await get_return_with_details(return_id, db)
    
    if return_request.invoice.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if return_request.status != "pending":
        raise HTTPException(status_code=400, detail="Return request already processed")
    
    # Validate items
    for item_update in process_data.items:
        rr_item_result = await db.execute(
            select(ReturnRequestItem).where(ReturnRequestItem.id == item_update.invoice_item_id)
        )
        rr_item = rr_item_result.scalar_one_or_none()
        if not rr_item or rr_item.return_request_id != return_id:
            raise HTTPException(status_code=400, detail="Invalid return item")
        
        if item_update.approved_quantity + item_update.rejected_quantity > rr_item.quantity:
            raise HTTPException(status_code=400, detail="Approved + rejected quantity exceeds requested")
        
        rr_item.approved_quantity = item_update.approved_quantity
        rr_item.rejected_quantity = item_update.rejected_quantity
        rr_item.rejection_reason = item_update.rejection_reason
    
    if process_data.action == "approve":
        return_request.status = "approved"
        return_request.approved_at = datetime.utcnow()
        
        # If requires inspection, keep as approved but wait for inspection
        if return_request.requires_inspection:
            return_request.status = "approved_pending_inspection"
    else:
        return_request.status = "rejected"
    
    return_request.processed_by = current_user.id
    return_request.processed_at = datetime.utcnow()
    return_request.processor_notes = process_data.processor_notes
    
    await db.commit()
    return await get_return_with_details(return_id, db)


@router.post("/{return_id}/inspect", response_model=ReturnRequestResponse)
async def inspect_return(
    return_id: UUID,
    inspection_data: ReturnRequestInspectionRequest,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    return_request = await get_return_with_details(return_id, db)
    
    if return_request.invoice.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not return_request.requires_inspection:
        raise HTTPException(status_code=400, detail="This return does not require inspection")
    
    if return_request.status != "approved_pending_inspection":
        raise HTTPException(status_code=400, detail="Return not ready for inspection")
    
    return_request.inspection_passed = inspection_data.passed
    return_request.inspection_notes = inspection_data.notes
    return_request.inspected_by = current_user.id
    return_request.inspected_at = datetime.utcnow()
    
    if inspection_data.passed:
        return_request.status = "approved"
        return_request.approved_at = datetime.utcnow()
    else:
        return_request.status = "rejected"
    
    await db.commit()
    return await get_return_with_details(return_id, db)


@router.post("/{return_id}/receive", response_model=ReturnRequestResponse)
async def receive_return(
    return_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    """Mark return as physically received at warehouse"""
    return_request = await get_return_with_details(return_id, db)
    
    if return_request.invoice.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if return_request.status not in ["approved", "approved_pending_inspection"]:
        raise HTTPException(status_code=400, detail="Return must be approved before receiving")
    
    if return_request.requires_inspection and not return_request.inspection_passed:
        raise HTTPException(status_code=400, detail="Inspection required and not passed")
    
    # Restore inventory for approved items
    for rr_item in return_request.items:
        if rr_item.approved_quantity > 0:
            # Find the original batch
            batch_result = await db.execute(
                select(ProductBatch).join(Product, ProductBatch.product_id == Product.id)
                .where(
                    ProductBatch.batch_number == rr_item.batch_number,
                    Product.name == rr_item.product_name
                )
            )
            batch = batch_result.scalar_one_or_none()
            
            if batch:
                inventory_result = await db.execute(
                    select(Inventory).where(
                        Inventory.product_id == batch.product_id,
                        Inventory.batch_id == batch.id,
                        Inventory.warehouse_id == return_request.invoice.order.warehouse_id
                    )
                )
                inventory = inventory_result.scalar_one_or_none()
                if inventory:
                    inventory.quantity_on_hand += rr_item.approved_quantity
                    inventory.quantity_available += rr_item.approved_quantity
                    inventory.last_movement = datetime.utcnow()
    
    return_request.status = "received"
    return_request.received_at = datetime.utcnow()
    
    await db.commit()
    return await get_return_with_details(return_id, db)