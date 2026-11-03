from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import Optional
from datetime import datetime
from app.db.session import get_db
from app.core.security import get_current_active_user, require_super_admin, require_distributor_access, get_password_hash
from app.models import User, UserRole, UserStatus
from app.schemas import UserCreate, UserUpdate, UserResponse, UserListResponse, PaginationParams

router = APIRouter()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    # Check email uniqueness
    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    
    # Validate role-distributor/retailer association
    if user_data.role in [UserRole.DISTRIBUTOR_ADMIN, UserRole.DISTRIBUTOR_STAFF]:
        if not user_data.distributor_id:
            raise HTTPException(status_code=400, detail="Distributor ID required for distributor roles")
        dist_result = await db.execute(select(User).where(User.id == user_data.distributor_id))
        if not dist_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Distributor not found")
    
    if user_data.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        if not user_data.retailer_id:
            raise HTTPException(status_code=400, detail="Retailer ID required for retailer roles")
        ret_result = await db.execute(select(User).where(User.id == user_data.retailer_id))
        if not ret_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Retailer not found")
    
    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        phone=user_data.phone,
        role=user_data.role,
        distributor_id=user_data.distributor_id,
        retailer_id=user_data.retailer_id,
        status=UserStatus.ACTIVE if user_data.role == UserRole.SUPER_ADMIN else UserStatus.PENDING_VERIFICATION,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("", response_model=UserListResponse)
async def list_users(
    pagination: PaginationParams = Depends(),
    role: Optional[UserRole] = None,
    status: Optional[UserStatus] = None,
    distributor_id: Optional[UUID] = None,
    retailer_id: Optional[UUID] = None,
    search: Optional[str] = None,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    query = select(User)
    
    if role:
        query = query.where(User.role == role)
    if status:
        query = query.where(User.status == status)
    if distributor_id:
        query = query.where(User.distributor_id == distributor_id)
    if retailer_id:
        query = query.where(User.retailer_id == retailer_id)
    if search:
        query = query.where(
            or_(
                User.email.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
                User.phone.ilike(f"%{search}%")
            )
        )
    
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # Apply pagination
    query = query.offset((pagination.page - 1) * pagination.page_size).limit(pagination.page_size)
    query = query.order_by(User.created_at.desc())
    
    result = await db.execute(query)
    users = result.scalars().all()
    
    return UserListResponse(
        users=users,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    update_data: UserUpdate,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/{user_id}/verify", response_model=UserResponse)
async def verify_user(
    user_id: UUID,
    action: str = Query(..., pattern="^(approve|reject)$"),
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if action == "approve":
        user.status = UserStatus.ACTIVE
    else:
        user.status = UserStatus.REJECTED
    
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: UUID,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db)
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_deleted = True
    user.deleted_at = datetime.utcnow()
    user.is_active = False
    await db.commit()