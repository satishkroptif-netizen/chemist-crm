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
from app.models import ProductBatch, Product, Warehouse, Inventory, User, UserRole
from app.schemas import ProductBatchCreate, ProductBatchUpdate, ProductBatchResponse, PaginationParams

router = APIRouter()


@router.post("", response_model=ProductBatchResponse, status_code=status.HTTP_201_CREATED)
async def create_batch(
    batch_data: ProductBatchCreate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    # Validate product belongs to distributor
    result = await db.execute(
        select(Product).where(
            Product.id == batch_data.product_id,
            Product.distributor_id == current_user.distributor_id
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found or access denied")
    
    # Validate warehouse belongs to distributor
    result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == batch_data.warehouse_id,
            Warehouse.distributor_id == current_user.distributor_id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Warehouse not found or access denied")
    
    # Check batch number uniqueness for product+warehouse
    result = await db.execute(
        select(ProductBatch).where(
            ProductBatch.product_id == batch_data.product_id,
            ProductBatch.batch_number == batch_data.batch_number,
            ProductBatch.warehouse_id == batch_data.warehouse_id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Batch number already exists for this product and warehouse")
    
    # Validate dates
    if batch_data.expiry_date < batch_data.manufacture_date:
        raise HTTPException(status_code=400, detail="Expiry date must be after manufacture date")
    
    if batch_data.expiry_date < date.today():
        raise HTTPException(status_code=400, detail="Expiry date cannot be in the past")
    
    batch = ProductBatch(
        **batch_data.model_dump(),
        available_quantity=batch_data.received_quantity,
    )
    db.add(batch)
    await db.flush()  # Flush to get batch.id before creating inventory
    
    # Create or update inventory
    inventory_result = await db.execute(
        select(Inventory).where(
            Inventory.product_id == batch_data.product_id,
            Inventory.batch_id == batch.id,
            Inventory.warehouse_id == batch_data.warehouse_id
        )
    )
    inventory = inventory_result.scalar_one_or_none()
    
    if inventory:
        inventory.quantity_on_hand += batch_data.received_quantity
        inventory.quantity_available += batch_data.received_quantity
        inventory.last_movement = datetime.utcnow()
    else:
        inventory = Inventory(
            product_id=batch_data.product_id,
            batch_id=batch.id,
            warehouse_id=batch_data.warehouse_id,
            quantity_on_hand=batch_data.received_quantity,
            quantity_available=batch_data.received_quantity,
            last_movement=datetime.utcnow(),
        )
        db.add(inventory)
    
    await db.commit()
    await db.refresh(batch)
    return await get_batch_with_details(batch.id, db)


async def get_batch_with_details(batch_id: UUID, db: AsyncSession) -> ProductBatchResponse:
    result = await db.execute(
        select(ProductBatch)
        .options(
            joinedload(ProductBatch.product).joinedload(Product.manufacturer),
            joinedload(ProductBatch.warehouse)
        )
        .where(ProductBatch.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    # Calculate days to expiry
    days_to_expiry = (batch.expiry_date - date.today()).days
    batch.days_to_expiry = days_to_expiry
    batch.is_expiring_soon = days_to_expiry <= 90  # From settings
    
    return batch


@router.get("", response_model=List[ProductBatchResponse])
async def list_batches(
    product_id: Optional[UUID] = None,
    warehouse_id: Optional[UUID] = None,
    is_active: Optional[bool] = True,
    expiring_soon: Optional[bool] = None,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    query = select(ProductBatch).options(
        joinedload(ProductBatch.product).joinedload(Product.manufacturer),
        joinedload(ProductBatch.warehouse)
    ).join(Product).where(Product.distributor_id == current_user.distributor_id)
    
    if product_id:
        query = query.where(ProductBatch.product_id == product_id)
    if warehouse_id:
        query = query.where(ProductBatch.warehouse_id == warehouse_id)
    if is_active is not None:
        query = query.where(ProductBatch.is_active == is_active)
    if expiring_soon:
        from app.core.config import get_settings
        settings = get_settings()
        threshold_date = date.today() + timedelta(days=settings.EXPIRY_WARNING_DAYS)
        query = query.where(
            ProductBatch.expiry_date <= threshold_date,
            ProductBatch.expiry_date >= date.today(),
            ProductBatch.available_quantity > 0
        )
    
    query = query.order_by(ProductBatch.expiry_date)
    
    result = await db.execute(query)
    batches = result.scalars().all()
    
    # Calculate days to expiry for each
    for batch in batches:
        days_to_expiry = (batch.expiry_date - date.today()).days
        batch.days_to_expiry = days_to_expiry
        batch.is_expiring_soon = days_to_expiry <= 90
    
    return batches


@router.get("/{batch_id}", response_model=ProductBatchResponse)
async def get_batch(
    batch_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    batch = await get_batch_with_details(batch_id, db)
    
    # Verify access through product
    if batch.product.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return batch


@router.patch("/{batch_id}", response_model=ProductBatchResponse)
async def update_batch(
    batch_id: UUID,
    update_data: ProductBatchUpdate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    batch = await get_batch_with_details(batch_id, db)
    
    if batch.product.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Validate dates if changing
    manufacture_date = update_data.manufacture_date or batch.manufacture_date
    expiry_date = update_data.expiry_date or batch.expiry_date
    if expiry_date < manufacture_date:
        raise HTTPException(status_code=400, detail="Expiry date must be after manufacture date")
    
    # Check batch number uniqueness if changing
    if update_data.batch_number and update_data.batch_number != batch.batch_number:
        result = await db.execute(
            select(ProductBatch).where(
                ProductBatch.product_id == batch.product_id,
                ProductBatch.batch_number == update_data.batch_number,
                ProductBatch.warehouse_id == batch.warehouse_id,
                ProductBatch.id != batch_id
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Batch number already exists")
    
    # Handle quantity changes
    old_received = batch.received_quantity
    new_received = update_data.received_quantity if update_data.received_quantity is not None else old_received
    
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(batch, field, value)
    
    # Adjust inventory if received quantity changed
    if new_received != old_received:
        diff = new_received - old_received
        batch.available_quantity += diff
        
        # Update inventory
        inventory_result = await db.execute(
            select(Inventory).where(
                Inventory.product_id == batch.product_id,
                Inventory.batch_id == batch.id,
                Inventory.warehouse_id == batch.warehouse_id
            )
        )
        inventory = inventory_result.scalar_one_or_none()
        if inventory:
            inventory.quantity_on_hand += diff
            inventory.quantity_available += diff
            inventory.last_movement = datetime.utcnow()
    
    await db.commit()
    return await get_batch_with_details(batch_id, db)


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_batch(
    batch_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    batch = await get_batch_with_details(batch_id, db)
    
    if batch.product.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if batch.available_quantity > 0:
        raise HTTPException(status_code=400, detail="Cannot delete batch with available stock")
    
    batch.is_deleted = True
    batch.deleted_at = datetime.utcnow()
    batch.is_active = False
    await db.commit()