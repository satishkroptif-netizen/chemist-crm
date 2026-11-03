from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from uuid import UUID
from typing import Optional
from datetime import datetime
from app.db.session import get_db
from app.core.security import get_current_active_user, require_distributor_access
from app.models import Manufacturer, User, UserRole
from app.schemas import ManufacturerCreate, ManufacturerUpdate, ManufacturerResponse, PaginationParams

router = APIRouter()


@router.post("", response_model=ManufacturerResponse, status_code=status.HTTP_201_CREATED)
async def create_manufacturer(
    manufacturer_data: ManufacturerCreate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    # Check name uniqueness
    result = await db.execute(select(Manufacturer).where(Manufacturer.name == manufacturer_data.name))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Manufacturer name already exists")
    
    # Check code uniqueness
    result = await db.execute(select(Manufacturer).where(Manufacturer.code == manufacturer_data.code))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Manufacturer code already exists")
    
    # Check GSTIN uniqueness if provided
    if manufacturer_data.gstin:
        result = await db.execute(select(Manufacturer).where(Manufacturer.gstin == manufacturer_data.gstin))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="GSTIN already registered")
    
    manufacturer = Manufacturer(**manufacturer_data.model_dump())
    db.add(manufacturer)
    await db.commit()
    await db.refresh(manufacturer)
    return manufacturer


@router.get("", response_model=list[ManufacturerResponse])
async def list_manufacturers(
    is_active: Optional[bool] = True,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Manufacturer)
    
    if is_active is not None:
        query = query.where(Manufacturer.is_active == is_active)
    if search:
        query = query.where(
            or_(
                Manufacturer.name.ilike(f"%{search}%"),
                Manufacturer.code.ilike(f"%{search}%"),
                Manufacturer.contact_person.ilike(f"%{search}%"),
            )
        )
    
    query = query.order_by(Manufacturer.name)
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{manufacturer_id}", response_model=ManufacturerResponse)
async def get_manufacturer(
    manufacturer_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Manufacturer).where(Manufacturer.id == manufacturer_id))
    manufacturer = result.scalar_one_or_none()
    if not manufacturer:
        raise HTTPException(status_code=404, detail="Manufacturer not found")
    return manufacturer


@router.patch("/{manufacturer_id}", response_model=ManufacturerResponse)
async def update_manufacturer(
    manufacturer_id: UUID,
    update_data: ManufacturerUpdate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Manufacturer).where(Manufacturer.id == manufacturer_id))
    manufacturer = result.scalar_one_or_none()
    if not manufacturer:
        raise HTTPException(status_code=404, detail="Manufacturer not found")
    
    # Check name uniqueness if changing
    if update_data.name and update_data.name != manufacturer.name:
        result = await db.execute(select(Manufacturer).where(Manufacturer.name == update_data.name))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Manufacturer name already exists")
    
    # Check GSTIN uniqueness if changing
    if update_data.gstin and update_data.gstin != manufacturer.gstin:
        result = await db.execute(select(Manufacturer).where(Manufacturer.gstin == update_data.gstin))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="GSTIN already registered")
    
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(manufacturer, field, value)
    
    await db.commit()
    await db.refresh(manufacturer)
    return manufacturer


@router.delete("/{manufacturer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_manufacturer(
    manufacturer_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Manufacturer).where(Manufacturer.id == manufacturer_id))
    manufacturer = result.scalar_one_or_none()
    if not manufacturer:
        raise HTTPException(status_code=404, detail="Manufacturer not found")
    
    # Check for associated products
    from app.models import Product
    result = await db.execute(select(Product).where(Product.manufacturer_id == manufacturer_id).limit(1))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Cannot delete manufacturer with associated products")
    
    manufacturer.is_deleted = True
    manufacturer.deleted_at = datetime.utcnow()
    manufacturer.is_active = False
    await db.commit()