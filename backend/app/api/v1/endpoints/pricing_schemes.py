from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload
from uuid import UUID
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime
from app.db.session import get_db
from app.core.security import get_current_active_user, require_distributor_access
from app.models import PricingScheme, Product, ProductCategory, Retailer, User, UserRole, SchemeType
from app.schemas import PricingSchemeCreate, PricingSchemeUpdate, PricingSchemeResponse, PaginationParams

router = APIRouter()


@router.post("", response_model=PricingSchemeResponse, status_code=status.HTTP_201_CREATED)
async def create_pricing_scheme(
    scheme_data: PricingSchemeCreate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    if not distributor_id:
        raise HTTPException(status_code=403, detail="User not associated with a distributor")
    
    # Validate scheme config based on type
    _validate_scheme_config(scheme_data.scheme_type, scheme_data.scheme_config)
    
    # Validate product IDs if provided
    if scheme_data.applicable_product_ids:
        result = await db.execute(
            select(Product).where(
                Product.id.in_(scheme_data.applicable_product_ids),
                Product.distributor_id == distributor_id
            )
        )
        if len(result.scalars().all()) != len(scheme_data.applicable_product_ids):
            raise HTTPException(status_code=400, detail="One or more products not found or access denied")
    
    # Validate category IDs if provided
    if scheme_data.applicable_category_ids:
        result = await db.execute(
            select(ProductCategory).where(ProductCategory.id.in_(scheme_data.applicable_category_ids))
        )
        if len(result.scalars().all()) != len(scheme_data.applicable_category_ids):
            raise HTTPException(status_code=400, detail="One or more categories not found")
    
    # Validate retailer IDs if provided
    if scheme_data.applicable_retailer_ids:
        result = await db.execute(
            select(Retailer).where(
                Retailer.id.in_(scheme_data.applicable_retailer_ids),
                Retailer.distributor_id == distributor_id
            )
        )
        if len(result.scalars().all()) != len(scheme_data.applicable_retailer_ids):
            raise HTTPException(status_code=400, detail="One or more retailers not found or access denied")
    
    # Validate dates
    if scheme_data.end_date and scheme_data.end_date < scheme_data.start_date:
        raise HTTPException(status_code=400, detail="End date must be after start date")
    
    scheme = PricingScheme(**scheme_data.model_dump(), distributor_id=distributor_id)
    db.add(scheme)
    await db.commit()
    await db.refresh(scheme)
    return scheme


def _validate_scheme_config(scheme_type: SchemeType, config: dict):
    """Validate scheme configuration based on type"""
    if scheme_type == SchemeType.BUY_GET_FREE:
        required = ["buy_qty", "free_qty"]
        for field in required:
            if field not in config:
                raise HTTPException(status_code=400, detail=f"Missing required field for BUY_GET_FREE: {field}")
        if config["buy_qty"] <= 0 or config["free_qty"] <= 0:
            raise HTTPException(status_code=400, detail="buy_qty and free_qty must be positive")
    
    elif scheme_type == SchemeType.VOLUME_DISCOUNT:
        if "tiers" not in config or not isinstance(config["tiers"], list):
            raise HTTPException(status_code=400, detail="VOLUME_DISCOUNT requires 'tiers' array")
        for tier in config["tiers"]:
            if "min_qty" not in tier or "discount_pct" not in tier:
                raise HTTPException(status_code=400, detail="Each tier requires min_qty and discount_pct")
            if tier["min_qty"] <= 0 or tier["discount_pct"] < 0 or tier["discount_pct"] > 100:
                raise HTTPException(status_code=400, detail="Invalid tier values")
    
    elif scheme_type == SchemeType.NET_RATE:
        if "product_id" not in config or "net_rate" not in config:
            raise HTTPException(status_code=400, detail="NET_RATE requires product_id and net_rate")
        if config["net_rate"] < 0:
            raise HTTPException(status_code=400, detail="net_rate must be non-negative")
    
    elif scheme_type == SchemeType.FLAT_DISCOUNT:
        required = ["min_order_value", "discount_amount"]
        for field in required:
            if field not in config:
                raise HTTPException(status_code=400, detail=f"Missing required field for FLAT_DISCOUNT: {field}")
        if config["min_order_value"] < 0 or config["discount_amount"] < 0:
            raise HTTPException(status_code=400, detail="Values must be non-negative")


@router.get("", response_model=List[PricingSchemeResponse])
async def list_pricing_schemes(
    is_active: Optional[bool] = True,
    scheme_type: Optional[SchemeType] = None,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    if not distributor_id:
        raise HTTPException(status_code=403, detail="User not associated with a distributor")
    
    query = select(PricingScheme).where(PricingScheme.distributor_id == distributor_id)
    
    if is_active is not None:
        query = query.where(PricingScheme.is_active == is_active)
    if scheme_type:
        query = query.where(PricingScheme.scheme_type == scheme_type)
    
    query = query.order_by(PricingScheme.priority.desc(), PricingScheme.start_date)
    
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/applicable")
async def get_applicable_schemes(
    retailer_id: UUID,
    product_ids: List[UUID] = Query(...),
    order_value: Decimal = Query(..., ge=0),
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    """Get all applicable pricing schemes for a retailer and product list"""
    distributor_id = current_user.distributor_id
    if not distributor_id:
        raise HTTPException(status_code=403, detail="User not associated with a distributor")
    
    # Verify retailer belongs to distributor
    result = await db.execute(
        select(Retailer).where(Retailer.id == retailer_id, Retailer.distributor_id == distributor_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Retailer not found or access denied")
    
    today = date.today()
    query = select(PricingScheme).where(
        PricingScheme.distributor_id == distributor_id,
        PricingScheme.is_active == True,
        PricingScheme.start_date <= today,
        (PricingScheme.end_date.is_(None)) | (PricingScheme.end_date >= today),
        (PricingScheme.min_order_value.is_(None)) | (PricingScheme.min_order_value <= order_value),
    )
    
    result = await db.execute(query)
    all_schemes = result.scalars().all()
    
    # Filter applicable schemes
    applicable = []
    for scheme in all_schemes:
        # Check product applicability
        if scheme.applicable_product_ids:
            if not any(pid in scheme.applicable_product_ids for pid in product_ids):
                continue
        if scheme.applicable_category_ids:
            # Would need to check product categories - simplified for now
            pass
        if scheme.applicable_retailer_ids:
            if retailer_id not in scheme.applicable_retailer_ids:
                continue
        
        applicable.append(scheme)
    
    # Sort by priority
    applicable.sort(key=lambda s: s.priority, reverse=True)
    
    return applicable


@router.get("/{scheme_id}", response_model=PricingSchemeResponse)
async def get_pricing_scheme(
    scheme_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    result = await db.execute(
        select(PricingScheme).where(
            PricingScheme.id == scheme_id,
            PricingScheme.distributor_id == distributor_id
        )
    )
    scheme = result.scalar_one_or_none()
    if not scheme:
        raise HTTPException(status_code=404, detail="Pricing scheme not found")
    return scheme


@router.patch("/{scheme_id}", response_model=PricingSchemeResponse)
async def update_pricing_scheme(
    scheme_id: UUID,
    update_data: PricingSchemeUpdate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    result = await db.execute(
        select(PricingScheme).where(
            PricingScheme.id == scheme_id,
            PricingScheme.distributor_id == distributor_id
        )
    )
    scheme = result.scalar_one_or_none()
    if not scheme:
        raise HTTPException(status_code=404, detail="Pricing scheme not found")
    
    # Validate scheme config if changing type or config
    if update_data.scheme_config or update_data.scheme_type:
        scheme_type = update_data.scheme_type or scheme.scheme_type
        scheme_config = update_data.scheme_config or scheme.scheme_config
        _validate_scheme_config(scheme_type, scheme_config)
    
    # Validate dates
    start_date = update_data.start_date or scheme.start_date
    end_date = update_data.end_date if update_data.end_date is not None else scheme.end_date
    if end_date and end_date < start_date:
        raise HTTPException(status_code=400, detail="End date must be after start date")
    
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(scheme, field, value)
    
    await db.commit()
    await db.refresh(scheme)
    return scheme


@router.delete("/{scheme_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pricing_scheme(
    scheme_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    result = await db.execute(
        select(PricingScheme).where(
            PricingScheme.id == scheme_id,
            PricingScheme.distributor_id == distributor_id
        )
    )
    scheme = result.scalar_one_or_none()
    if not scheme:
        raise HTTPException(status_code=404, detail="Pricing scheme not found")
    
    scheme.is_deleted = True
    scheme.deleted_at = datetime.utcnow()
    scheme.is_active = False
    await db.commit()