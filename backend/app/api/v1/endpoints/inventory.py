from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, text
from sqlalchemy.orm import selectinload, joinedload
from uuid import UUID
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime, timedelta
from app.db.session import get_db
from app.core.security import get_current_active_user, require_distributor_access
from app.models import Inventory, ProductBatch, Product, Warehouse, StockMovement, User, UserRole
from app.schemas import InventoryResponse, StockMovementCreate, StockMovementResponse, PaginationParams

router = APIRouter()


@router.get("", response_model=List[InventoryResponse])
async def list_inventory(
    warehouse_id: Optional[UUID] = None,
    product_id: Optional[UUID] = None,
    low_stock_only: bool = False,
    expiring_soon: bool = False,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    query = select(Inventory).options(
        joinedload(Inventory.product).joinedload(Product.manufacturer),
        joinedload(Inventory.product).joinedload(Product.category),
        joinedload(Inventory.batch),
        joinedload(Inventory.warehouse)
    ).join(Product).where(Product.distributor_id == current_user.distributor_id)
    
    if warehouse_id:
        query = query.where(Inventory.warehouse_id == warehouse_id)
    if product_id:
        query = query.where(Inventory.product_id == product_id)
    if low_stock_only:
        query = query.where(Inventory.quantity_available <= Product.reorder_level)
    if expiring_soon:
        from app.core.config import get_settings
        settings = get_settings()
        threshold_date = date.today() + timedelta(days=settings.EXPIRY_WARNING_DAYS)
        query = query.join(ProductBatch).where(
            ProductBatch.expiry_date <= threshold_date,
            ProductBatch.expiry_date >= date.today()
        )
    
    query = query.where(Inventory.quantity_available > 0)
    query = query.order_by(Inventory.quantity_available)
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/summary")
async def inventory_summary(
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    """Get inventory summary statistics"""
    # Total products with stock
    total_products = await db.scalar(
        select(func.count(func.distinct(Inventory.product_id)))
        .join(Product)
        .where(Product.distributor_id == current_user.distributor_id, Inventory.quantity_available > 0)
    )
    
    # Low stock products
    low_stock = await db.scalar(
        select(func.count(func.distinct(Inventory.product_id)))
        .join(Product)
        .where(
            Product.distributor_id == current_user.distributor_id,
            Inventory.quantity_available > 0,
            Inventory.quantity_available <= Product.reorder_level
        )
    )
    
    # Expiring soon
    from app.core.config import get_settings
    settings = get_settings()
    threshold_date = date.today() + timedelta(days=settings.EXPIRY_WARNING_DAYS)
    expiring = await db.scalar(
        select(func.count(func.distinct(Inventory.product_id)))
        .join(Product)
        .join(ProductBatch, Inventory.batch_id == ProductBatch.id)
        .where(
            Product.distributor_id == current_user.distributor_id,
            Inventory.quantity_available > 0,
            ProductBatch.expiry_date <= threshold_date,
            ProductBatch.expiry_date >= date.today()
        )
    )
    
    # Total stock value (at trade price)
    value_result = await db.execute(
        select(func.sum(Inventory.quantity_available * Product.trade_price))
        .join(Product)
        .where(Product.distributor_id == current_user.distributor_id, Inventory.quantity_available > 0)
    )
    total_value = value_result.scalar() or 0
    
    # By warehouse
    warehouse_query = select(
        Warehouse.name,
        func.sum(Inventory.quantity_available).label("total_qty"),
        func.sum(Inventory.quantity_available * Product.trade_price).label("total_value")
    ).join(Inventory).join(Product).where(
        Product.distributor_id == current_user.distributor_id,
        Inventory.quantity_available > 0
    ).group_by(Warehouse.id, Warehouse.name)
    warehouse_result = await db.execute(warehouse_query)
    by_warehouse = [
        {"warehouse": row.name, "total_quantity": row.total_qty, "total_value": float(row.total_value or 0)}
        for row in warehouse_result.all()
    ]
    
    return {
        "total_products_with_stock": total_products or 0,
        "low_stock_products": low_stock or 0,
        "expiring_soon_products": expiring or 0,
        "total_stock_value": float(total_value),
        "by_warehouse": by_warehouse,
    }


@router.get("/{inventory_id}", response_model=InventoryResponse)
async def get_inventory(
    inventory_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Inventory).options(
            joinedload(Inventory.product).joinedload(Product.manufacturer),
            joinedload(Inventory.product).joinedload(Product.category),
            joinedload(Inventory.batch),
            joinedload(Inventory.warehouse)
        ).where(Inventory.id == inventory_id)
    )
    inventory = result.scalar_one_or_none()
    if not inventory:
        raise HTTPException(status_code=404, detail="Inventory not found")
    
    if inventory.product.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return inventory


@router.post("/movements", response_model=StockMovementResponse, status_code=status.HTTP_201_CREATED)
async def create_stock_movement(
    movement_data: StockMovementCreate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    # Verify inventory belongs to distributor
    result = await db.execute(
        select(Inventory).options(joinedload(Inventory.product))
        .where(Inventory.id == movement_data.inventory_id)
    )
    inventory = result.scalar_one_or_none()
    if not inventory:
        raise HTTPException(status_code=404, detail="Inventory not found")
    
    if inventory.product.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Validate movement
    if movement_data.movement_type in ["out", "transfer"] and movement_data.quantity > inventory.quantity_available:
        raise HTTPException(status_code=400, detail="Insufficient available quantity")
    
    movement = StockMovement(
        **movement_data.model_dump(),
        performed_by=current_user.id,
    )
    db.add(movement)
    
    # Update inventory
    if movement_data.movement_type == "in":
        inventory.quantity_on_hand += movement_data.quantity
        inventory.quantity_available += movement_data.quantity
    elif movement_data.movement_type == "out":
        inventory.quantity_on_hand -= movement_data.quantity
        inventory.quantity_available -= movement_data.quantity
    elif movement_data.movement_type == "adjustment":
        # Adjustment sets the quantity to the specified value
        diff = movement_data.quantity - inventory.quantity_on_hand
        inventory.quantity_on_hand = movement_data.quantity
        inventory.quantity_available += diff
    
    inventory.last_movement = datetime.utcnow()
    inventory.last_stock_take = datetime.utcnow()
    
    await db.commit()
    await db.refresh(movement)
    return movement


@router.get("/{inventory_id}/movements", response_model=List[StockMovementResponse])
async def get_stock_movements(
    inventory_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    # Verify access
    result = await db.execute(
        select(Inventory).join(Product).where(
            Inventory.id == inventory_id,
            Product.distributor_id == current_user.distributor_id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Inventory not found")
    
    result = await db.execute(
        select(StockMovement)
        .where(StockMovement.inventory_id == inventory_id)
        .order_by(StockMovement.created_at.desc())
    )
    return result.scalars().all()


@router.post("/reserve", status_code=status.HTTP_200_OK)
async def reserve_stock(
    product_id: UUID,
    batch_id: UUID,
    warehouse_id: UUID,
    quantity: int,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    """Reserve stock for an order (pessimistic locking)"""
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")
    
    result = await db.execute(
        select(Inventory).options(joinedload(Inventory.product))
        .where(
            Inventory.product_id == product_id,
            Inventory.batch_id == batch_id,
            Inventory.warehouse_id == warehouse_id
        )
        .with_for_update()  # Pessimistic lock
    )
    inventory = result.scalar_one_or_none()
    if not inventory:
        raise HTTPException(status_code=404, detail="Inventory not found")
    
    if inventory.product.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if inventory.quantity_available < quantity:
        raise HTTPException(status_code=400, detail=f"Insufficient stock. Available: {inventory.quantity_available}")
    
    inventory.quantity_reserved += quantity
    inventory.quantity_available -= quantity
    inventory.last_movement = datetime.utcnow()
    
    await db.commit()
    
    return {"reserved": quantity, "available": inventory.quantity_available, "reserved_total": inventory.quantity_reserved}


@router.post("/release", status_code=status.HTTP_200_OK)
async def release_stock(
    product_id: UUID,
    batch_id: UUID,
    warehouse_id: UUID,
    quantity: int,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    """Release reserved stock"""
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")
    
    result = await db.execute(
        select(Inventory).options(joinedload(Inventory.product))
        .where(
            Inventory.product_id == product_id,
            Inventory.batch_id == batch_id,
            Inventory.warehouse_id == warehouse_id
        )
        .with_for_update()
    )
    inventory = result.scalar_one_or_none()
    if not inventory:
        raise HTTPException(status_code=404, detail="Inventory not found")
    
    if inventory.product.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if inventory.quantity_reserved < quantity:
        raise HTTPException(status_code=400, detail="Cannot release more than reserved")
    
    inventory.quantity_reserved -= quantity
    inventory.quantity_available += quantity
    inventory.last_movement = datetime.utcnow()
    
    await db.commit()
    
    return {"released": quantity, "available": inventory.quantity_available, "reserved_total": inventory.quantity_reserved}