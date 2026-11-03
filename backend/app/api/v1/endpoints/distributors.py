from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from uuid import UUID
from typing import Optional
from datetime import date, datetime
from app.db.session import get_db
from app.core.security import get_current_active_user, require_super_admin, require_distributor_access
from app.models import Distributor, User, UserRole
from app.schemas import DistributorCreate, DistributorUpdate, DistributorResponse, DistributorListResponse, PaginationParams

router = APIRouter()


@router.post("", response_model=DistributorResponse, status_code=status.HTTP_201_CREATED)
async def create_distributor(
    distributor_data: DistributorCreate,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    # Check GSTIN uniqueness
    result = await db.execute(select(Distributor).where(Distributor.gstin == distributor_data.gstin))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="GSTIN already registered")
    
    # Check drug license uniqueness
    result = await db.execute(select(Distributor).where(Distributor.drug_license_number == distributor_data.drug_license_number))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Drug license number already registered")
    
    # Check email uniqueness
    result = await db.execute(select(Distributor).where(Distributor.email == distributor_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    
    # Validate drug license expiry
    if distributor_data.drug_license_expiry < date.today():
        raise HTTPException(status_code=400, detail="Drug license has expired")
    
    distributor = Distributor(**distributor_data.model_dump())
    db.add(distributor)
    await db.commit()
    await db.refresh(distributor)
    return distributor


@router.get("", response_model=DistributorListResponse)
async def list_distributors(
    pagination: PaginationParams = Depends(),
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    query = select(Distributor)
    
    if is_active is not None:
        query = query.where(Distributor.is_active == is_active)
    if search:
        query = query.where(
            or_(
                Distributor.name.ilike(f"%{search}%"),
                Distributor.legal_name.ilike(f"%{search}%"),
                Distributor.gstin.ilike(f"%{search}%"),
                Distributor.email.ilike(f"%{search}%"),
            )
        )
    
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    query = query.offset((pagination.page - 1) * pagination.page_size).limit(pagination.page_size)
    query = query.order_by(Distributor.created_at.desc())
    
    result = await db.execute(query)
    distributors = result.scalars().all()
    
    return DistributorListResponse(
        distributors=distributors,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size
    )


@router.get("/{distributor_id}", response_model=DistributorResponse)
async def get_distributor(
    distributor_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # Distributors can only see their own data unless super admin
    if current_user.role not in [UserRole.SUPER_ADMIN] and current_user.distributor_id != distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = await db.execute(select(Distributor).where(Distributor.id == distributor_id))
    distributor = result.scalar_one_or_none()
    if not distributor:
        raise HTTPException(status_code=404, detail="Distributor not found")
    return distributor


@router.patch("/{distributor_id}", response_model=DistributorResponse)
async def update_distributor(
    distributor_id: UUID,
    update_data: DistributorUpdate,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Distributor).where(Distributor.id == distributor_id))
    distributor = result.scalar_one_or_none()
    if not distributor:
        raise HTTPException(status_code=404, detail="Distributor not found")
    
    # Check GSTIN uniqueness if changing
    if update_data.gstin and update_data.gstin != distributor.gstin:
        result = await db.execute(select(Distributor).where(Distributor.gstin == update_data.gstin))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="GSTIN already registered")
    
    # Check email uniqueness if changing
    if update_data.email and update_data.email != distributor.email:
        result = await db.execute(select(Distributor).where(Distributor.email == update_data.email))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already registered")
    
    # Validate drug license expiry if changing
    if update_data.drug_license_expiry and update_data.drug_license_expiry < date.today():
        raise HTTPException(status_code=400, detail="Drug license has expired")
    
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(distributor, field, value)
    
    await db.commit()
    await db.refresh(distributor)
    return distributor


@router.delete("/{distributor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_distributor(
    distributor_id: UUID,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Distributor).where(Distributor.id == distributor_id))
    distributor = result.scalar_one_or_none()
    if not distributor:
        raise HTTPException(status_code=404, detail="Distributor not found")
    
    distributor.is_deleted = True
    distributor.deleted_at = datetime.utcnow()
    distributor.is_active = False
    await db.commit()