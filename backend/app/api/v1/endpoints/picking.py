from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload, joinedload
from uuid import UUID
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime
from app.db.session import get_db
from app.core.security import get_current_active_user, require_distributor_access
from app.models import (
    Order, OrderItem, OrderStatus, ProductBatch, Inventory, Warehouse,
    Product, User, UserRole
)
from app.schemas import PickingSlipResponse, PickingSlipItemResponse, OrderResponse

router = APIRouter()


@router.get("/orders-ready", response_model=List[dict])
async def get_orders_ready_for_picking(
    warehouse_id: Optional[UUID] = None,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    """Get orders that are approved and ready for picking"""
    query = select(Order).options(
        joinedload(Order.retailer),
        joinedload(Order.warehouse),
        selectinload(Order.items).joinedload(OrderItem.product),
        selectinload(Order.items).joinedload(OrderItem.batch)
    ).where(
        Order.distributor_id == current_user.distributor_id,
        Order.status == OrderStatus.APPROVED_BY_CREDIT
    )
    
    if warehouse_id:
        query = query.where(Order.warehouse_id == warehouse_id)
    
    query = query.order_by(Order.order_date)
    
    result = await db.execute(query)
    orders = result.scalars().all()
    
    return [
        {
            "order_id": str(order.id),
            "order_number": order.order_number,
            "retailer_name": order.retailer.name,
            "order_date": order.order_date.isoformat(),
            "total_items": len(order.items),
            "total_qty": sum(item.ordered_qty for item in order.items),
            "warehouse": order.warehouse.name if order.warehouse else None
        }
        for order in orders
    ]


@router.post("/{order_id}/start", response_model=PickingSlipResponse)
async def start_picking(
    order_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    """Start picking process for an order - generates picking slip"""
    order_result = await db.execute(
        select(Order).options(
            joinedload(Order.warehouse),
            selectinload(Order.items).joinedload(OrderItem.product),
            selectinload(Order.items).joinedload(OrderItem.batch)
        ).where(Order.id == order_id)
    )
    order = order_result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if order.status != OrderStatus.APPROVED_BY_CREDIT:
        raise HTTPException(status_code=400, detail="Order must be approved by credit before picking")
    
    # Generate picking slip number
    today = date.today()
    prefix = f"PICK{today.strftime('%Y%m%d')}"
    count_result = await db.execute(
        select(func.count()).where(
            select(Order).where(Order.status == OrderStatus.PICKING).exists()
        )
    )
    count = await db.scalar(
        select(func.count(Order.id)).where(
            Order.distributor_id == current_user.distributor_id,
            Order.status == OrderStatus.PICKING,
            Order.created_at >= today
        )
    ) or 0
    
    slip_number = f"{prefix}{count + 1:05d}"
    
    # Update order status
    order.status = OrderStatus.PICKING
    
    # Create status history
    from app.models import OrderStatusHistory
    status_history = OrderStatusHistory(
        order_id=order.id,
        from_status=OrderStatus.APPROVED_BY_CREDIT,
        to_status=OrderStatus.PICKING,
        changed_by=current_user.id,
        notes="Picking started"
    )
    db.add(status_history)
    
    await db.commit()
    
    # Build picking slip items grouped by batch
    slip_items = []
    for item in order.items:
        if item.batch_id:
            # Get batch details
            batch_result = await db.execute(
                select(ProductBatch).where(ProductBatch.id == item.batch_id)
            )
            batch = batch_result.scalar_one()
            
            slip_items.append(PickingSlipItemResponse(
                product_id=item.product_id,
                product_name=item.product_name,
                product_sku=item.product_sku,
                batch_id=item.batch_id,
                batch_number=batch.batch_number,
                expiry_date=batch.expiry_date,
                quantity=item.ordered_qty,
                warehouse_location=None,  # Could be added to warehouse model
                is_instrument=item.product.is_instrument if item.product else False,
                instrument_check_required=item.product.is_instrument if item.product else False,
            ))
        else:
            # Should not happen - batch should be allocated
            product_result = await db.execute(select(Product).where(Product.id == item.product_id))
            product = product_result.scalar_one()
            
            # Find available batch
            batch_result = await db.execute(
                select(ProductBatch).join(Inventory).where(
                    ProductBatch.product_id == item.product_id,
                    ProductBatch.warehouse_id == order.warehouse_id,
                    ProductBatch.available_quantity >= item.ordered_qty
                ).order_by(ProductBatch.expiry_date)
            )
            batch = batch_result.scalars().first()
            
            if batch:
                slip_items.append(PickingSlipItemResponse(
                    product_id=item.product_id,
                    product_name=item.product_name,
                    product_sku=item.product_sku,
                    batch_id=batch.id,
                    batch_number=batch.batch_number,
                    expiry_date=batch.expiry_date,
                    quantity=item.ordered_qty,
                    warehouse_location=None,
                    is_instrument=product.is_instrument,
                    instrument_check_required=product.is_instrument,
                ))
    
    return PickingSlipResponse(
        id=order.id,
        order_id=order.id,
        warehouse_id=order.warehouse_id,
        slip_number=slip_number,
        status="picking",
        items=slip_items,
        created_by=current_user.id,
    )


@router.post("/{order_id}/complete", response_model=OrderResponse)
async def complete_picking(
    order_id: UUID,
    packed_items: List[dict],  # [{"order_item_id": UUID, "packed_qty": int, "batch_id": UUID, "instrument_check_passed": bool}]
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    """Complete picking and mark items as packed"""
    order_result = await db.execute(
        select(Order).options(
            selectinload(Order.items).joinedload(OrderItem.batch)
        ).where(Order.id == order_id)
    )
    order = order_result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if order.status != OrderStatus.PICKING:
        raise HTTPException(status_code=400, detail="Order is not in picking status")
    
    # Update packed quantities
    for packed in packed_items:
        item_result = await db.execute(
            select(OrderItem).where(OrderItem.id == packed["order_item_id"])
        )
        item = item_result.scalar_one_or_none()
        if not item or item.order_id != order_id:
            raise HTTPException(status_code=400, detail="Invalid order item")
        
        packed_qty = packed.get("packed_qty", item.ordered_qty)
        if packed_qty > item.ordered_qty:
            raise HTTPException(status_code=400, detail="Packed quantity exceeds ordered quantity")
        
        item.packed_qty = packed_qty
        item.is_packed = packed_qty == item.ordered_qty
        
        # Instrument check
        if packed.get("instrument_check_passed") is not None:
            if item.product and item.product.is_instrument:
                # Log instrument check
                pass
    
    # Check if all items packed
    all_packed = all(item.is_packed for item in order.items)
    
    if all_packed:
        order.status = OrderStatus.INVOICED
        order.invoiced_at = datetime.utcnow()
        
        # Create status history
        from app.models import OrderStatusHistory
        status_history = OrderStatusHistory(
            order_id=order.id,
            from_status=OrderStatus.PICKING,
            to_status=OrderStatus.INVOICED,
            changed_by=current_user.id,
            notes="Picking completed, ready for invoicing"
        )
        db.add(status_history)
    
    await db.commit()
    await db.refresh(order)
    
    # Return full order
    from app.api.v1.endpoints.orders import get_order_with_details
    return await get_order_with_details(order_id, db)


@router.get("/{order_id}/slip", response_model=PickingSlipResponse)
async def get_picking_slip(
    order_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    """Get picking slip for an order"""
    order_result = await db.execute(
        select(Order).options(
            joinedload(Order.warehouse),
            selectinload(Order.items).joinedload(OrderItem.product),
            selectinload(Order.items).joinedload(OrderItem.batch)
        ).where(Order.id == order_id)
    )
    order = order_result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if order.status not in [OrderStatus.PICKING, OrderStatus.INVOICED, OrderStatus.DISPATCHED]:
        raise HTTPException(status_code=400, detail="Order not in picking stage")
    
    slip_items = []
    for item in order.items:
        if item.batch_id:
            batch_result = await db.execute(
                select(ProductBatch).where(ProductBatch.id == item.batch_id)
            )
            batch = batch_result.scalar_one()
            
            slip_items.append(PickingSlipItemResponse(
                product_id=item.product_id,
                product_name=item.product_name,
                product_sku=item.product_sku,
                batch_id=item.batch_id,
                batch_number=batch.batch_number,
                expiry_date=batch.expiry_date,
                quantity=item.packed_qty or item.ordered_qty,
                warehouse_location=None,
                is_instrument=item.product.is_instrument if item.product else False,
                instrument_check_required=item.product.is_instrument if item.product else False,
                instrument_check_passed=item.product.is_instrument if item.product else None,
            ))
    
    return PickingSlipResponse(
        id=order.id,
        order_id=order.id,
        warehouse_id=order.warehouse_id,
        slip_number=f"PICK{order.order_number[-8:]}",
        status=order.status.value if order.status in [OrderStatus.PICKING, OrderStatus.INVOICED, OrderStatus.DISPATCHED] else "completed",
        items=slip_items,
        created_by=order.created_by,
    )