from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import Optional
from datetime import datetime
from app.db.session import get_db
from app.core.security import get_current_active_user, require_distributor_access
from app.models import ProductCategory, User, UserRole
from app.schemas import CategoryCreate, CategoryUpdate, CategoryResponse, PaginationParams

router = APIRouter()


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_data: CategoryCreate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    # Validate parent exists if provided
    if category_data.parent_id:
        result = await db.execute(select(ProductCategory).where(ProductCategory.id == category_data.parent_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Parent category not found")
    
    category = ProductCategory(**category_data.model_dump())
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    parent_id: Optional[UUID] = None,
    is_active: Optional[bool] = True,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(ProductCategory).options(selectinload(ProductCategory.children))
    
    if parent_id:
        query = query.where(ProductCategory.parent_id == parent_id)
    else:
        query = query.where(ProductCategory.parent_id.is_(None))
    
    if is_active is not None:
        query = query.where(ProductCategory.is_active == is_active)
    
    query = query.order_by(ProductCategory.sort_order, ProductCategory.name)
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ProductCategory).options(selectinload(ProductCategory.children)).where(ProductCategory.id == category_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    update_data: CategoryUpdate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ProductCategory).where(ProductCategory.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Validate parent exists and is not self
    if update_data.parent_id:
        if update_data.parent_id == category_id:
            raise HTTPException(status_code=400, detail="Category cannot be its own parent")
        result = await db.execute(select(ProductCategory).where(ProductCategory.id == update_data.parent_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Parent category not found")
    
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    
    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(ProductCategory).where(ProductCategory.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Check for children
    result = await db.execute(select(ProductCategory).where(ProductCategory.parent_id == category_id))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Cannot delete category with children")
    
    category.is_deleted = True
    category.deleted_at = datetime.utcnow()
    category.is_active = False
    await db.commit()