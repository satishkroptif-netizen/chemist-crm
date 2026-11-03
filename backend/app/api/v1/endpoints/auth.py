from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from app.db.session import get_db
from app.core.security import (
    verify_password, get_password_hash, create_access_token, create_refresh_token,
    get_current_active_user, decode_token
)
from app.core.config import get_settings
from app.core.exceptions import BusinessRuleError
from app.models import User, UserRole, UserStatus
from app.schemas import (
    LoginRequest, Token, UserCreate, UserResponse, UserUpdate,
    UserListResponse, ChangePasswordRequest, PaginationParams, RefreshTokenRequest
)

settings = get_settings()

router = APIRouter()


@router.post("/login", response_model=Token)
async def login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    
    if user.status == UserStatus.SUSPENDED:
        raise HTTPException(status_code=403, detail="Account is suspended")
    
    if user.status == UserStatus.PENDING_VERIFICATION:
        raise HTTPException(status_code=403, detail="Account pending verification")
    
    if user.status == UserStatus.REJECTED:
        raise HTTPException(status_code=403, detail="Account rejected")
    
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.utcnow()
    await db.commit()
    
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "distributor_id": str(user.distributor_id) if user.distributor_id else None,
        "retailer_id": str(user.retailer_id) if user.retailer_id else None,
    }
    
    return Token(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token({"sub": str(user.id)}),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(request: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(request.refresh_token)
        if payload.type != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    result = await db.execute(select(User).where(User.id == payload.sub))
    user = result.scalar_one_or_none()
    
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "distributor_id": str(user.distributor_id) if user.distributor_id else None,
        "retailer_id": str(user.retailer_id) if user.retailer_id else None,
    }
    
    return Token(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token({"sub": str(user.id)}),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    if not verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    current_user.hashed_password = get_password_hash(request.new_password)
    await db.commit()
    
    return {"message": "Password changed successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return current_user