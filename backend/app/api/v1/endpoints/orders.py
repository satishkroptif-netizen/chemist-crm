from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, text
from sqlalchemy.orm import selectinload, joinedload
from uuid import UUID
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime, timedelta
from app.db.session import get_db
from app.core.security import get_current_active_user, require_distributor_access, require_retailer_access
from app.models import (
    Order, OrderItem, OrderStatus, OrderStatusHistory,
    Product, ProductBatch, Inventory, Retailer, Warehouse, PricingScheme,
    User, UserRole, ProductSubstitute
)
from app.schemas import OrderCreate, OrderUpdate, OrderResponse, OrderListResponse, OrderStatusUpdate, OrderCreditCheckRequest, OrderItemCreate, PaginationParams
from app.core.exceptions import InsufficientStockError, CreditLimitExceededError, ExpiryTooSoonError, InvalidStateTransitionError
from app.core.config import get_settings

router = APIRouter()

settings = get_settings()

VALID_TRANSITIONS = {
    OrderStatus.DRAFT: [OrderStatus.SUBMITTED, OrderStatus.CANCELLED],
    OrderStatus.SUBMITTED: [OrderStatus.APPROVED_BY_CREDIT, OrderStatus.CANCELLED],
    OrderStatus.APPROVED_BY_CREDIT: [OrderStatus.PICKING, OrderStatus.CANCELLED],
    OrderStatus.PICKING: [OrderStatus.INVOICED, OrderStatus.CANCELLED],
    OrderStatus.INVOICED: [OrderStatus.DISPATCHED, OrderStatus.CANCELLED],
    OrderStatus.DISPATCHED: [OrderStatus.DELIVERED, OrderStatus.CANCELLED],
    OrderStatus.DELIVERED: [OrderStatus.CLOSED],
    OrderStatus.CLOSED: [],
    OrderStatus.CANCELLED: [],
    OrderStatus.RETURN_REQUESTED: [OrderStatus.RETURN_APPROVED, OrderStatus.RETURN_REJECTED],
    OrderStatus.RETURN_APPROVED: [OrderStatus.CREDIT_NOTE_ISSUED],
    OrderStatus.RETURN_REJECTED: [OrderStatus.CLOSED],
    OrderStatus.CREDIT_NOTE_ISSUED: [OrderStatus.CLOSED],
}


async def generate_order_number(db: AsyncSession, distributor_id: UUID) -> str:
    """Generate unique order number"""
    today = date.today()
    prefix = f"ORD{today.strftime('%Y%m%d')}"
    
    result = await db.execute(
        select(func.count(Order.id)).where(
            Order.distributor_id == distributor_id,
            Order.order_number.like(f"{prefix}%")
        )
    )
    count = result.scalar() or 0
    return f"{prefix}{count + 1:05d}"


async def apply_pricing_schemes(
    db: AsyncSession,
    distributor_id: UUID,
    retailer_id: UUID,
    items: List[OrderItemCreate],
    order_value: Decimal
) -> List[dict]:
    """Apply pricing schemes to order items"""
    from app.models import PricingScheme, SchemeType
    
    today = date.today()
    schemes_result = await db.execute(
        select(PricingScheme).where(
            PricingScheme.distributor_id == distributor_id,
            PricingScheme.is_active == True,
            PricingScheme.start_date <= today,
            (PricingScheme.end_date.is_(None)) | (PricingScheme.end_date >= today),
            (PricingScheme.min_order_value.is_(None)) | (PricingScheme.min_order_value <= order_value),
        ).order_by(PricingScheme.priority.desc())
    )
    schemes = schemes_result.scalars().all()
    
    results = []
    for item in items:
        product_result = await db.execute(
            select(Product).where(Product.id == item.product_id)
        )
        product = product_result.scalar_one()
        
        unit_price = product.trade_price
        discount_per_unit = Decimal("0")
        applied_scheme = None
        
        for scheme in schemes:
            # Check retailer applicability
            if scheme.applicable_retailer_ids and retailer_id not in scheme.applicable_retailer_ids:
                continue
            
            # Check product applicability
            if scheme.applicable_product_ids and item.product_id not in scheme.applicable_product_ids:
                continue
            
            # Check category applicability
            if scheme.applicable_category_ids and product.category_id not in scheme.applicable_category_ids:
                continue
            
            # Apply scheme
            if scheme.scheme_type == SchemeType.BUY_GET_FREE:
                config = scheme.scheme_config
                buy_qty = config.get("buy_qty", 0)
                free_qty = config.get("free_qty", 0)
                if item.ordered_qty >= buy_qty:
                    free_units = (item.ordered_qty // buy_qty) * free_qty
                    discount_per_unit = (product.trade_price * free_units) / item.ordered_qty
                    applied_scheme = {
                        "type": "buy_get_free",
                        "buy_qty": buy_qty,
                        "free_qty": free_qty,
                        "free_units": free_units
                    }
                    break
            
            elif scheme.scheme_type == SchemeType.VOLUME_DISCOUNT:
                config = scheme.scheme_config
                tiers = config.get("tiers", [])
                applicable_discount = Decimal("0")
                for tier in tiers:
                    if item.ordered_qty >= tier["min_qty"]:
                        applicable_discount = max(applicable_discount, Decimal(str(tier["discount_pct"])))
                if applicable_discount > 0:
                    discount_per_unit = product.trade_price * applicable_discount / 100
                    applied_scheme = {
                        "type": "volume_discount",
                        "discount_pct": float(applicable_discount)
                    }
                    break
            
            elif scheme.scheme_type == SchemeType.NET_RATE:
                config = scheme.scheme_config
                if config.get("product_id") == str(item.product_id):
                    unit_price = Decimal(str(config["net_rate"]))
                    discount_per_unit = product.trade_price - unit_price
                    applied_scheme = {
                        "type": "net_rate",
                        "net_rate": str(unit_price)
                    }
                    break
            
            elif scheme.scheme_type == SchemeType.FLAT_DISCOUNT:
                config = scheme.scheme_config
                if order_value >= config.get("min_order_value", 0):
                    discount_amount = min(
                        Decimal(str(config["discount_amount"])),
                        scheme.max_discount_per_order or Decimal(str(config["discount_amount"]))
                    )
                    discount_per_unit = discount_amount / sum(i.ordered_qty for i in items)
                    applied_scheme = {
                        "type": "flat_discount",
                        "discount_amount": str(discount_amount)
                    }
                    break
        
        unit_price = product.trade_price - discount_per_unit
        results.append({
            "product_id": item.product_id,
            "unit_price": unit_price.quantize(Decimal("0.01")),
            "discount_per_unit": discount_per_unit.quantize(Decimal("0.01")),
            "scheme_applied": applied_scheme,
            "mrp": product.mrp,
        })
    
    return results


async def allocate_batches_fefo(
    db: AsyncSession,
    distributor_id: UUID,
    warehouse_id: UUID,
    items: List[OrderItemCreate]
) -> List[dict]:
    """Allocate batches using FEFO (First Expired First Out)"""
    allocations = []
    
    for item in items:
        # Get product to check FEFO settings
        product_result = await db.execute(
            select(Product).where(Product.id == item.product_id)
        )
        product = product_result.scalar_one()
        
        # Get available batches ordered by expiry (FEFO)
        batches_result = await db.execute(
            select(ProductBatch)
            .join(Inventory)
            .where(
                ProductBatch.product_id == item.product_id,
                ProductBatch.warehouse_id == warehouse_id,
                ProductBatch.is_active == True,
                ProductBatch.available_quantity > 0,
                ProductBatch.expiry_date >= date.today() + timedelta(days=settings.EXPIRY_WARNING_DAYS)
            )
            .order_by(ProductBatch.expiry_date)
            .with_for_update()
        )
        batches = batches_result.scalars().all()
        
        if not batches:
            # Check if there are batches but expiring soon
            expiring_result = await db.execute(
                select(ProductBatch)
                .join(Inventory)
                .where(
                    ProductBatch.product_id == item.product_id,
                    ProductBatch.warehouse_id == warehouse_id,
                    ProductBatch.is_active == True,
                    ProductBatch.available_quantity > 0,
                    ProductBatch.expiry_date < date.today() + timedelta(days=settings.EXPIRY_WARNING_DAYS)
                )
                .order_by(ProductBatch.expiry_date)
            )
            expiring = expiring_result.scalars().all()
            if expiring:
                raise ExpiryTooSoonError(
                    product.name, expiring[0].batch_number,
                    expiring[0].expiry_date.isoformat(),
                    (expiring[0].expiry_date - date.today()).days,
                    settings.EXPIRY_WARNING_DAYS
                )
            raise InsufficientStockError(product.name, item.ordered_qty, 0)
        
        remaining_qty = item.ordered_qty
        item_allocations = []
        
        for batch in batches:
            if remaining_qty <= 0:
                break
            
            inventory_result = await db.execute(
                select(Inventory).where(
                    Inventory.product_id == item.product_id,
                    Inventory.batch_id == batch.id,
                    Inventory.warehouse_id == warehouse_id
                ).with_for_update()
            )
            inventory = inventory_result.scalar_one()
            
            alloc_qty = min(remaining_qty, inventory.quantity_available)
            if alloc_qty > 0:
                item_allocations.append({
                    "batch_id": batch.id,
                    "batch_number": batch.batch_number,
                    "expiry_date": batch.expiry_date,
                    "quantity": alloc_qty,
                })
                remaining_qty -= alloc_qty
                
                # Reserve stock
                inventory.quantity_reserved += alloc_qty
                inventory.quantity_available -= alloc_qty
        
        if remaining_qty > 0:
            raise InsufficientStockError(product.name, item.ordered_qty, item.ordered_qty - remaining_qty)
        
        allocations.append({
            "product_id": item.product_id,
            "allocations": item_allocations,
        })
    
    return allocations


async def check_credit_limit(db: AsyncSession, retailer_id: UUID, order_amount: Decimal) -> tuple[bool, str]:
    """Check if retailer has sufficient credit limit"""
    retailer_result = await db.execute(select(Retailer).where(Retailer.id == retailer_id))
    retailer = retailer_result.scalar_one()
    
    available_credit = retailer.credit_limit - retailer.used_credit
    
    if order_amount > available_credit:
        return False, f"Order amount {order_amount} exceeds available credit {available_credit}"
    
    return True, ""


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # Determine distributor
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        retailer_result = await db.execute(select(Retailer).where(Retailer.id == current_user.retailer_id))
        retailer = retailer_result.scalar_one()
        if not retailer.is_verified:
            raise HTTPException(status_code=403, detail="Retailer not verified")
        distributor_id = retailer.distributor_id
        retailer_id = current_user.retailer_id
    else:
        distributor_id = current_user.distributor_id
        retailer_id = order_data.retailer_id
    
    if not distributor_id:
        raise HTTPException(status_code=403, detail="User not associated with a distributor")
    
    # Verify retailer belongs to distributor
    retailer_result = await db.execute(
        select(Retailer).where(Retailer.id == retailer_id, Retailer.distributor_id == distributor_id)
    )
    retailer = retailer_result.scalar_one_or_none()
    if not retailer:
        raise HTTPException(status_code=404, detail="Retailer not found or access denied")
    
    if not retailer.is_verified:
        raise HTTPException(status_code=403, detail="Retailer not verified")
    
    # Verify warehouse if provided
    warehouse_id = order_data.warehouse_id
    if not warehouse_id:
        # Use default warehouse
        warehouse_result = await db.execute(
            select(Warehouse).where(
                Warehouse.distributor_id == distributor_id,
                Warehouse.is_default == True,
                Warehouse.is_active == True
            )
        )
        warehouse = warehouse_result.scalar_one_or_none()
        if not warehouse:
            raise HTTPException(status_code=400, detail="No default warehouse configured")
        warehouse_id = warehouse.id
    else:
        warehouse_result = await db.execute(
            select(Warehouse).where(
                Warehouse.id == warehouse_id,
                Warehouse.distributor_id == distributor_id,
                Warehouse.is_active == True
            )
        )
        if not warehouse_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Warehouse not found or access denied")
    
    # Validate items
    product_ids = [item.product_id for item in order_data.items]
    products_result = await db.execute(
        select(Product).where(Product.id.in_(product_ids), Product.distributor_id == distributor_id)
    )
    products = {p.id: p for p in products_result.scalars().all()}
    
    if len(products) != len(product_ids):
        raise HTTPException(status_code=400, detail="One or more products not found")
    
    # Check for duplicates
    if len(set(product_ids)) != len(product_ids):
        raise HTTPException(status_code=400, detail="Duplicate products in order")
    
    # Apply pricing schemes
    order_value = sum(p.trade_price * item.ordered_qty for item, p in zip(order_data.items, [products[i.product_id] for i in order_data.items]))
    pricing_results = await apply_pricing_schemes(db, distributor_id, retailer_id, order_data.items, order_value)
    
    # Allocate batches using FEFO
    batch_allocations = await allocate_batches_fefo(db, distributor_id, warehouse_id, order_data.items)
    
    # Calculate totals
    subtotal = Decimal("0")
    discount_amount = Decimal("0")
    tax_amount = Decimal("0")
    
    order_items = []
    for i, item_data in enumerate(order_data.items):
        product = products[item_data.product_id]
        pricing = pricing_results[i]
        allocation = batch_allocations[i]
        
        # Use first batch for order item (primary batch)
        primary_batch = allocation["allocations"][0]
        
        line_subtotal = pricing["unit_price"] * item_data.ordered_qty
        line_discount = pricing["discount_per_unit"] * item_data.ordered_qty
        line_tax = line_subtotal * product.gst_rate / 100
        line_total = line_subtotal + line_tax
        
        subtotal += line_subtotal
        discount_amount += line_discount
        tax_amount += line_tax
        
        order_items.append({
            "product_id": item_data.product_id,
            "batch_id": primary_batch["batch_id"],
            "product_name": product.name,
            "product_sku": product.sku,
            "product_generic_name": product.generic_name,
            "batch_number": primary_batch["batch_number"],
            "expiry_date": primary_batch["expiry_date"],
            "hsn_code": product.hsn_code,
            "gst_rate": product.gst_rate,
            "unit_of_measure": product.unit_of_measure,
            "pack_size": product.pack_size,
            "ordered_qty": item_data.ordered_qty,
            "unit_price": pricing["unit_price"],
            "mrp": pricing["mrp"],
            "discount_per_unit": pricing["discount_per_unit"],
            "scheme_applied": pricing["scheme_applied"],
            "line_subtotal": line_subtotal,
            "line_discount": line_discount,
            "line_tax": line_tax,
            "line_total": line_total,
        })
    
    total_amount = subtotal + tax_amount
    
    # Check credit limit
    credit_ok, credit_msg = await check_credit_limit(db, retailer_id, total_amount)
    
    # Create order
    order = Order(
        order_number=await generate_order_number(db, distributor_id),
        status=OrderStatus.DRAFT,
        distributor_id=distributor_id,
        retailer_id=retailer_id,
        warehouse_id=warehouse_id,
        created_by=current_user.id,
        subtotal=subtotal,
        discount_amount=discount_amount,
        tax_amount=tax_amount,
        total_amount=total_amount,
        credit_checked=False,
        credit_check_passed=credit_ok,
        credit_check_notes=credit_msg if not credit_ok else None,
        order_date=date.today(),
        expected_delivery_date=order_data.expected_delivery_date,
        shipping_address=order_data.shipping_address or retailer.address,
        shipping_city=order_data.shipping_city or retailer.city,
        shipping_state=order_data.shipping_state or retailer.state,
        shipping_pincode=order_data.shipping_pincode or retailer.pincode,
        shipping_contact_name=order_data.shipping_contact_name,
        shipping_contact_phone=order_data.shipping_contact_phone,
        retailer_notes=order_data.retailer_notes,
    )
    db.add(order)
    await db.flush()
    
    # Create order items
    for item_data in order_items:
        order_item = OrderItem(
            order_id=order.id,
            **item_data
        )
        db.add(order_item)
    
    # Create status history
    status_history = OrderStatusHistory(
        order_id=order.id,
        from_status=None,
        to_status=OrderStatus.DRAFT,
        changed_by=current_user.id,
        notes="Order created"
    )
    db.add(status_history)
    
    await db.commit()
    await db.refresh(order)
    return await get_order_with_details(order.id, db)


async def get_order_with_details(order_id: UUID, db: AsyncSession) -> OrderResponse:
    result = await db.execute(
        select(Order).options(
            joinedload(Order.retailer),
            joinedload(Order.distributor),
            joinedload(Order.warehouse),
            selectinload(Order.items).joinedload(OrderItem.product).joinedload(Product.manufacturer),
            selectinload(Order.items).joinedload(OrderItem.batch),
            selectinload(Order.status_history).joinedload(OrderStatusHistory.changed_by_user)
        ).where(Order.id == order_id)
    )
    return result.scalar_one()


@router.get("", response_model=OrderListResponse)
async def list_orders(
    pagination: PaginationParams = Depends(),
    status: Optional[OrderStatus] = None,
    retailer_id: Optional[UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Order).options(
        joinedload(Order.retailer),
        joinedload(Order.distributor),
        joinedload(Order.warehouse),
        selectinload(Order.items),
        selectinload(Order.status_history),
    )
    
    # Filter by distributor/retailer based on role
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        query = query.where(Order.retailer_id == current_user.retailer_id)
    else:
        query = query.where(Order.distributor_id == current_user.distributor_id)
        if retailer_id:
            query = query.where(Order.retailer_id == retailer_id)
    
    if status:
        query = query.where(Order.status == status)
    if date_from:
        query = query.where(Order.order_date >= date_from)
    if date_to:
        query = query.where(Order.order_date <= date_to)
    
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    query = query.offset((pagination.page - 1) * pagination.page_size).limit(pagination.page_size)
    query = query.order_by(Order.created_at.desc())
    
    result = await db.execute(query)
    orders = result.scalars().all()
    
    return OrderListResponse(
        orders=orders,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    order = await get_order_with_details(order_id, db)
    
    # Check access
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        if order.retailer_id != current_user.retailer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if order.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return order


@router.patch("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: UUID,
    update_data: OrderUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    order = await get_order_with_details(order_id, db)
    
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        if order.retailer_id != current_user.retailer_id:
            raise HTTPException(status_code=403, detail="Access denied")
        # Retailers can only update DRAFT orders
        if order.status != OrderStatus.DRAFT:
            raise HTTPException(status_code=400, detail="Can only update draft orders")
    else:
        if order.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(order, field, value)
    
    await db.commit()
    return await get_order_with_details(order_id, db)


@router.post("/{order_id}/submit", response_model=OrderResponse)
async def submit_order(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    order = await get_order_with_details(order_id, db)
    
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        if order.retailer_id != current_user.retailer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if order.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    if order.status != OrderStatus.DRAFT:
        raise InvalidStateTransitionError("Order", order.status.value, OrderStatus.SUBMITTED.value)
    
    # Check credit if not already checked
    if not order.credit_checked:
        credit_ok, credit_msg = await check_credit_limit(db, order.retailer_id, order.total_amount)
        order.credit_checked = True
        order.credit_check_passed = credit_ok
        order.credit_check_notes = credit_msg if not credit_ok else None
        order.credit_checked_at = datetime.utcnow()
        order.credit_checked_by = current_user.id
    
    order.status = OrderStatus.SUBMITTED
    
    status_history = OrderStatusHistory(
        order_id=order.id,
        from_status=OrderStatus.DRAFT,
        to_status=OrderStatus.SUBMITTED,
        changed_by=current_user.id,
        notes="Order submitted by retailer"
    )
    db.add(status_history)
    
    await db.commit()
    return await get_order_with_details(order_id, db)


@router.post("/{order_id}/credit-check", response_model=OrderResponse)
async def credit_check_order(
    order_id: UUID,
    check_request: OrderCreditCheckRequest,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    order = await get_order_with_details(order_id, db)
    
    if order.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if order.status != OrderStatus.SUBMITTED:
        raise InvalidStateTransitionError("Order", order.status.value, OrderStatus.APPROVED_BY_CREDIT.value)
    
    if check_request.approve:
        order.status = OrderStatus.APPROVED_BY_CREDIT
        order.credit_check_passed = True
        order.approved_by = current_user.id
        order.approved_at = datetime.utcnow()
        notes = "Credit approved"
    else:
        order.status = OrderStatus.CANCELLED
        order.cancellation_reason = check_request.notes or "Credit check failed"
        notes = f"Credit rejected: {check_request.notes or 'No reason provided'}"
    
    order.credit_check_notes = check_request.notes
    order.credit_checked_at = datetime.utcnow()
    order.credit_checked_by = current_user.id
    
    status_history = OrderStatusHistory(
        order_id=order.id,
        from_status=OrderStatus.SUBMITTED,
        to_status=order.status,
        changed_by=current_user.id,
        notes=notes
    )
    db.add(status_history)
    
    await db.commit()
    return await get_order_with_details(order_id, db)


@router.post("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: UUID,
    status_update: OrderStatusUpdate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    order = await get_order_with_details(order_id, db)
    
    if order.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if status_update.to_status not in VALID_TRANSITIONS.get(order.status, []):
        raise InvalidStateTransitionError("Order", order.status.value, status_update.to_status.value)
    
    from_status = order.status
    order.status = status_update.to_status
    
    # Set timestamps based on status
    now = datetime.utcnow()
    if status_update.to_status == OrderStatus.APPROVED_BY_CREDIT:
        order.approved_by = current_user.id
        order.approved_at = now
    elif status_update.to_status == OrderStatus.INVOICED:
        order.invoiced_at = now
    elif status_update.to_status == OrderStatus.DISPATCHED:
        order.dispatched_at = now
    elif status_update.to_status == OrderStatus.DELIVERED:
        order.delivered_at = now
    elif status_update.to_status == OrderStatus.CLOSED:
        order.closed_at = now
    elif status_update.to_status == OrderStatus.CANCELLED:
        order.cancellation_reason = status_update.notes
    
    status_history = OrderStatusHistory(
        order_id=order.id,
        from_status=from_status,
        to_status=status_update.to_status,
        changed_by=current_user.id,
        notes=status_update.notes
    )
    db.add(status_history)
    
    await db.commit()
    return await get_order_with_details(order_id, db)


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: UUID,
    reason: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    order = await get_order_with_details(order_id, db)
    
    # Check access
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        if order.retailer_id != current_user.retailer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if order.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    if order.status not in [OrderStatus.DRAFT, OrderStatus.SUBMITTED, OrderStatus.APPROVED_BY_CREDIT]:
        raise InvalidStateTransitionError("Order", order.status.value, OrderStatus.CANCELLED.value)
    
    # Release reserved stock
    for item in order.items:
        if item.batch_id:
            inventory_result = await db.execute(
                select(Inventory).where(
                    Inventory.product_id == item.product_id,
                    Inventory.batch_id == item.batch_id,
                    Inventory.warehouse_id == order.warehouse_id
                ).with_for_update()
            )
            inventory = inventory_result.scalar_one_or_none()
            if inventory:
                inventory.quantity_reserved -= item.ordered_qty
                inventory.quantity_available += item.ordered_qty
                inventory.last_movement = datetime.utcnow()
    
    order.status = OrderStatus.CANCELLED
    order.cancellation_reason = reason
    
    status_history = OrderStatusHistory(
        order_id=order.id,
        from_status=order.status,
        to_status=OrderStatus.CANCELLED,
        changed_by=current_user.id,
        notes=f"Cancelled: {reason}"
    )
    db.add(status_history)
    
    await db.commit()
    return await get_order_with_details(order_id, db)


@router.get("/{order_id}/substitutes")
async def get_order_substitutes(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get substitute suggestions for out-of-stock items in order"""
    order = await get_order_with_details(order_id, db)
    
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        if order.retailer_id != current_user.retailer_id:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        if order.distributor_id != current_user.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    substitutes = []
    for item in order.items:
        if item.batch_id is None:  # Not allocated
            sub_result = await db.execute(
                select(ProductSubstitute)
                .options(
                    joinedload(ProductSubstitute.substitute_product).joinedload(Product.manufacturer),
                    joinedload(ProductSubstitute.substitute_product).joinedload(Product.category)
                )
                .where(ProductSubstitute.product_id == item.product_id)
                .order_by(ProductSubstitute.priority)
            )
            product_subs = sub_result.scalars().all()
            
            # Filter to in-stock substitutes
            for sub in product_subs:
                stock_result = await db.execute(
                    select(func.sum(Inventory.quantity_available))
                    .where(
                        Inventory.product_id == sub.substitute_product_id,
                        Inventory.quantity_available > 0
                    )
                )
                available = stock_result.scalar() or 0
                if available > 0:
                    substitutes.append({
                        "original_product_id": item.product_id,
                        "original_product_name": item.product_name,
                        "substitute": sub.substitute_product,
                        "available_quantity": available,
                        "is_generic_equivalent": sub.is_generic_equivalent,
                    })
    
    return substitutes