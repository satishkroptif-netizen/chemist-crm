from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import Optional
from datetime import date, datetime
from app.db.session import get_db
from app.core.security import get_current_active_user, require_super_admin, require_distributor_access, require_retailer_access
from app.models import Retailer, User, UserRole, UserStatus
from app.schemas import RetailerCreate, RetailerUpdate, RetailerResponse, RetailerListResponse, RetailerVerifyRequest, PaginationParams

router = APIRouter()


@router.post("", response_model=RetailerResponse, status_code=status.HTTP_201_CREATED)
async def create_retailer(
    retailer_data: RetailerCreate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    # Check GSTIN uniqueness
    result = await db.execute(select(Retailer).where(Retailer.gstin == retailer_data.gstin))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="GSTIN already registered")
    
    # Check drug license uniqueness
    result = await db.execute(select(Retailer).where(Retailer.drug_license_number == retailer_data.drug_license_number))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Drug license number already registered")
    
    # Check email uniqueness
    result = await db.execute(select(Retailer).where(Retailer.email == retailer_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    
    # Validate drug license expiry
    if retailer_data.drug_license_expiry < date.today():
        raise HTTPException(status_code=400, detail="Drug license has expired")
    
    # Determine distributor
    distributor_id = retailer_data.distributor_id
    if current_user.role != UserRole.SUPER_ADMIN:
        distributor_id = current_user.distributor_id
        if not distributor_id:
            raise HTTPException(status_code=403, detail="User not associated with a distributor")
    
    retailer = Retailer(
        **retailer_data.model_dump(exclude={"distributor_id"}),
        distributor_id=distributor_id,
        is_verified=False,
        verified_at=None,
        verified_by=None,
    )
    db.add(retailer)
    await db.commit()
    await db.refresh(retailer)
    return retailer


@router.get("", response_model=RetailerListResponse)
async def list_retailers(
    pagination: PaginationParams = Depends(),
    is_verified: Optional[bool] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Retailer)
    
    # Filter by distributor for non-super-admin
    if current_user.role != UserRole.SUPER_ADMIN:
        query = query.where(Retailer.distributor_id == current_user.distributor_id)
    
    if is_verified is not None:
        query = query.where(Retailer.is_verified == is_verified)
    if is_active is not None:
        query = query.where(Retailer.is_active == is_active)
    if search:
        query = query.where(
            or_(
                Retailer.name.ilike(f"%{search}%"),
                Retailer.legal_name.ilike(f"%{search}%"),
                Retailer.gstin.ilike(f"%{search}%"),
                Retailer.email.ilike(f"%{search}%"),
            )
        )
    
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    query = query.offset((pagination.page - 1) * pagination.page_size).limit(pagination.page_size)
    query = query.order_by(Retailer.created_at.desc())
    
    result = await db.execute(query)
    retailers = result.scalars().all()
    
    return RetailerListResponse(
        retailers=retailers,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size
    )


@router.get("/{retailer_id}", response_model=RetailerResponse)
async def get_retailer(
    retailer_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Retailer).where(Retailer.id == retailer_id))
    retailer = result.scalar_one_or_none()
    if not retailer:
        raise HTTPException(status_code=404, detail="Retailer not found")
    
    # Check access
    if current_user.role not in [UserRole.SUPER_ADMIN]:
        if current_user.role in [UserRole.DISTRIBUTOR_ADMIN, UserRole.DISTRIBUTOR_STAFF]:
            if retailer.distributor_id != current_user.distributor_id:
                raise HTTPException(status_code=403, detail="Access denied")
        elif current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
            if current_user.retailer_id != retailer_id:
                raise HTTPException(status_code=403, detail="Access denied")
    
    return retailer


@router.patch("/{retailer_id}", response_model=RetailerResponse)
async def update_retailer(
    retailer_id: UUID,
    update_data: RetailerUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Retailer).where(Retailer.id == retailer_id))
    retailer = result.scalar_one_or_none()
    if not retailer:
        raise HTTPException(status_code=404, detail="Retailer not found")
    
    # Check access
    if current_user.role not in [UserRole.SUPER_ADMIN, UserRole.DISTRIBUTOR_ADMIN]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    if current_user.role == UserRole.DISTRIBUTOR_ADMIN and retailer.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check GSTIN uniqueness if changing
    if update_data.gstin and update_data.gstin != retailer.gstin:
        result = await db.execute(select(Retailer).where(Retailer.gstin == update_data.gstin))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="GSTIN already registered")
    
    # Check email uniqueness if changing
    if update_data.email and update_data.email != retailer.email:
        result = await db.execute(select(Retailer).where(Retailer.email == update_data.email))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already registered")
    
    # Validate drug license expiry if changing
    if update_data.drug_license_expiry and update_data.drug_license_expiry < date.today():
        raise HTTPException(status_code=400, detail="Drug license has expired")
    
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(retailer, field, value)
    
    await db.commit()
    await db.refresh(retailer)
    return retailer


@router.post("/{retailer_id}/verify", response_model=RetailerResponse)
async def verify_retailer(
    retailer_id: UUID,
    verify_request: RetailerVerifyRequest,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Retailer).where(Retailer.id == retailer_id))
    retailer = result.scalar_one_or_none()
    if not retailer:
        raise HTTPException(status_code=404, detail="Retailer not found")
    
    if current_user.role != UserRole.SUPER_ADMIN and retailer.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if verify_request.action == "approve":
        retailer.is_verified = True
        retailer.verified_at = datetime.utcnow()
        retailer.verified_by = current_user.id
    else:
        retailer.is_verified = False
        retailer.verified_at = None
        retailer.verified_by = None
    
    await db.commit()
    await db.refresh(retailer)
    return retailer


@router.delete("/{retailer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_retailer(
    retailer_id: UUID,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Retailer).where(Retailer.id == retailer_id))
    retailer = result.scalar_one_or_none()
    if not retailer:
        raise HTTPException(status_code=404, detail="Retailer not found")
    
    retailer.is_deleted = True
    retailer.deleted_at = datetime.utcnow()
    retailer.is_active = False
    await db.commit()