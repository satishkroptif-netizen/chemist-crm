from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from uuid import UUID
from typing import Optional
from datetime import datetime
from app.db.session import get_db
from app.core.security import get_current_active_user, require_distributor_access
from app.models import Warehouse, User, UserRole, WarehouseType
from app.schemas import WarehouseCreate, WarehouseUpdate, WarehouseResponse, PaginationParams

router = APIRouter()


@router.post("", response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    warehouse_data: WarehouseCreate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    if not distributor_id:
        raise HTTPException(status_code=403, detail="User not associated with a distributor")
    
    # Check code uniqueness within distributor
    result = await db.execute(
        select(Warehouse).where(
            Warehouse.distributor_id == distributor_id,
            Warehouse.code == warehouse_data.code
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Warehouse code already exists")
    
    # If setting as default, unset other defaults
    if warehouse_data.is_default:
        result = await db.execute(
            select(Warehouse).where(
                Warehouse.distributor_id == distributor_id,
                Warehouse.is_default == True
            )
        )
        existing_default = result.scalar_one_or_none()
        if existing_default:
            existing_default.is_default = False
    
    warehouse = Warehouse(**warehouse_data.model_dump(), distributor_id=distributor_id)
    db.add(warehouse)
    await db.commit()
    await db.refresh(warehouse)
    return warehouse


@router.get("", response_model=list[WarehouseResponse])
async def list_warehouses(
    is_active: Optional[bool] = None,
    warehouse_type: Optional[WarehouseType] = None,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    if not distributor_id:
        raise HTTPException(status_code=403, detail="User not associated with a distributor")
    
    query = select(Warehouse).where(Warehouse.distributor_id == distributor_id)
    
    if is_active is not None:
        query = query.where(Warehouse.is_active == is_active)
    if warehouse_type:
        query = query.where(Warehouse.warehouse_type == warehouse_type)
    
    query = query.order_by(Warehouse.is_default.desc(), Warehouse.name)
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{warehouse_id}", response_model=WarehouseResponse)
async def get_warehouse(
    warehouse_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    if not distributor_id:
        raise HTTPException(status_code=403, detail="User not associated with a distributor")
    
    result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.distributor_id == distributor_id
        )
    )
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return warehouse


@router.patch("/{warehouse_id}", response_model=WarehouseResponse)
async def update_warehouse(
    warehouse_id: UUID,
    update_data: WarehouseUpdate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    if not distributor_id:
        raise HTTPException(status_code=403, detail="User not associated with a distributor")
    
    result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.distributor_id == distributor_id
        )
    )
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    
    # If setting as default, unset other defaults
    if update_data.is_default is True and not warehouse.is_default:
        result = await db.execute(
            select(Warehouse).where(
                Warehouse.distributor_id == distributor_id,
                Warehouse.is_default == True,
                Warehouse.id != warehouse_id
            )
        )
        existing_default = result.scalar_one_or_none()
        if existing_default:
            existing_default.is_default = False
    
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(warehouse, field, value)
    
    await db.commit()
    await db.refresh(warehouse)
    return warehouse


@router.delete("/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_warehouse(
    warehouse_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    if not distributor_id:
        raise HTTPException(status_code=403, detail="User not associated with a distributor")
    
    result = await db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id,
            Warehouse.distributor_id == distributor_id
        )
    )
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    
    if warehouse.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default warehouse")
    
    warehouse.is_deleted = True
    warehouse.deleted_at = datetime.utcnow()
    warehouse.is_active = False
    await db.commit()