from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, text
from sqlalchemy.orm import selectinload, joinedload
from uuid import UUID
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime, timedelta
from app.db.session import get_db
from app.core.security import get_current_active_user, require_distributor_access, require_retailer_access
from app.models import Product, ProductCategory, Manufacturer, ProductBatch, Inventory, Warehouse, ProductSubstitute, User, UserRole
from app.schemas import ProductCreate, ProductUpdate, ProductResponse, ProductListResponse, ProductSearchFilters, PaginationParams, ProductSubstituteCreate, ProductSubstituteResponse

router = APIRouter()


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    if not distributor_id:
        raise HTTPException(status_code=403, detail="User not associated with a distributor")
    
    # Check SKU uniqueness within distributor
    result = await db.execute(
        select(Product).where(
            Product.distributor_id == distributor_id,
            Product.sku == product_data.sku
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="SKU already exists for this distributor")
    
    # Check barcode uniqueness if provided
    if product_data.barcode:
        result = await db.execute(select(Product).where(Product.barcode == product_data.barcode))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Barcode already exists")
    
    # Validate category
    result = await db.execute(select(ProductCategory).where(ProductCategory.id == product_data.category_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Validate manufacturer
    result = await db.execute(select(Manufacturer).where(Manufacturer.id == product_data.manufacturer_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Manufacturer not found")
    
    product = Product(**product_data.model_dump(), distributor_id=distributor_id)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return await get_product_with_details(product.id, db)


@router.get("", response_model=ProductListResponse)
async def list_products(
    pagination: PaginationParams = Depends(),
    filters: ProductSearchFilters = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        # Retailers see products from their distributor
        from app.models import Retailer
        result = await db.execute(select(Retailer).where(Retailer.id == current_user.retailer_id))
        retailer = result.scalar_one_or_none()
        if not retailer:
            raise HTTPException(status_code=404, detail="Retailer not found")
        distributor_id = retailer.distributor_id
    
    if not distributor_id:
        raise HTTPException(status_code=403, detail="User not associated with a distributor")
    
    query = select(Product).options(
        joinedload(Product.manufacturer),
        joinedload(Product.category)
    ).where(Product.distributor_id == distributor_id, Product.is_active == True)
    
    if not filters.in_stock_only:
        query = query.where(Product.is_discontinued == False)
    
    if filters.query:
        search_term = f"%{filters.query}%"
        query = query.where(
            or_(
                Product.name.ilike(search_term),
                Product.generic_name.ilike(search_term),
                Product.sku.ilike(search_term),
            )
        )
    
    if filters.category_id:
        query = query.where(Product.category_id == filters.category_id)
    
    if filters.manufacturer_id:
        query = query.where(Product.manufacturer_id == filters.manufacturer_id)
    
    if filters.dosage_form:
        query = query.where(Product.dosage_form == filters.dosage_form)
    
    if filters.is_instrument is not None:
        query = query.where(Product.is_instrument == filters.is_instrument)
    
    if filters.is_cold_chain is not None:
        query = query.where(Product.is_cold_chain == filters.is_cold_chain)
    
    if filters.min_price is not None:
        query = query.where(Product.trade_price >= filters.min_price)
    
    if filters.max_price is not None:
        query = query.where(Product.trade_price <= filters.max_price)
    
    if filters.expiry_within_days:
        # Join with batches to filter by expiry
        from app.models import ProductBatch
        subquery = select(ProductBatch.product_id).where(
            ProductBatch.expiry_date <= date.today() + timedelta(days=filters.expiry_within_days),
            ProductBatch.is_active == True,
            ProductBatch.available_quantity > 0
        ).distinct()
        query = query.where(Product.id.in_(subquery))
    
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    # Apply pagination
    query = query.offset((pagination.page - 1) * pagination.page_size).limit(pagination.page_size)
    query = query.order_by(Product.name)
    
    result = await db.execute(query)
    products = result.scalars().all()
    
    # Get available stock for each product
    product_ids = [p.id for p in products]
    if product_ids:
        stock_query = select(
            Inventory.product_id,
            func.sum(Inventory.quantity_available).label("total_available")
        ).where(
            Inventory.product_id.in_(product_ids),
            Inventory.quantity_available > 0
        ).group_by(Inventory.product_id)
        stock_result = await db.execute(stock_query)
        stock_map = {row.product_id: row.total_available for row in stock_result.all()}
        
        for product in products:
            product.available_stock = stock_map.get(product.id, 0)
    
    return ProductListResponse(
        products=products,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size
    )


async def get_product_with_details(product_id: UUID, db: AsyncSession) -> ProductResponse:
    result = await db.execute(
        select(Product)
        .options(
            joinedload(Product.manufacturer),
            joinedload(Product.category),
            selectinload(Product.batches).joinedload(ProductBatch.warehouse)
        )
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Get available stock
    stock_query = select(func.sum(Inventory.quantity_available)).where(
        Inventory.product_id == product_id,
        Inventory.quantity_available > 0
    )
    product.available_stock = await db.scalar(stock_query) or 0
    
    return product


@router.get("/search", response_model=ProductListResponse)
async def search_products(
    q: str = Query(..., min_length=2),
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Quick search for retailer portal - searches by brand, generic name, manufacturer"""
    distributor_id = current_user.distributor_id
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        from app.models import Retailer
        result = await db.execute(select(Retailer).where(Retailer.id == current_user.retailer_id))
        retailer = result.scalar_one_or_none()
        if not retailer:
            raise HTTPException(status_code=404, detail="Retailer not found")
        distributor_id = retailer.distributor_id
    
    if not distributor_id:
        raise HTTPException(status_code=403, detail="User not associated with a distributor")
    
    search_term = f"%{q}%"
    query = select(Product).options(
        joinedload(Product.manufacturer),
        joinedload(Product.category)
    ).where(
        Product.distributor_id == distributor_id,
        Product.is_active == True,
        Product.is_discontinued == False,
        or_(
            Product.name.ilike(search_term),
            Product.generic_name.ilike(search_term),
            Product.sku.ilike(search_term),
            Manufacturer.name.ilike(search_term),
        )
    ).join(Manufacturer)
    
    # Only show products with available stock
    subquery = select(Inventory.product_id).where(
        Inventory.quantity_available > 0
    ).distinct()
    query = query.where(Product.id.in_(subquery))
    
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)
    
    query = query.offset((pagination.page - 1) * pagination.page_size).limit(pagination.page_size)
    query = query.order_by(Product.name)
    
    result = await db.execute(query)
    products = result.scalars().all()
    
    return ProductListResponse(
        products=products,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=(total + pagination.page_size - 1) // pagination.page_size
    )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    product = await get_product_with_details(product_id, db)
    
    # Check access for retailers
    if current_user.role in [UserRole.RETAILER_ADMIN, UserRole.RETAILER_STAFF]:
        from app.models import Retailer
        result = await db.execute(select(Retailer).where(Retailer.id == current_user.retailer_id))
        retailer = result.scalar_one_or_none()
        if product.distributor_id != retailer.distributor_id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return product


@router.get("/{product_id}/substitutes", response_model=list[ProductSubstituteResponse])
async def get_product_substitutes(
    product_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get substitute products for a given product (for Substitute Finder)"""
    result = await db.execute(
        select(ProductSubstitute)
        .options(
            joinedload(ProductSubstitute.substitute_product).joinedload(Product.manufacturer),
            joinedload(ProductSubstitute.substitute_product).joinedload(Product.category)
        )
        .where(ProductSubstitute.product_id == product_id)
        .order_by(ProductSubstitute.priority)
    )
    substitutes = result.scalars().all()
    
    # Filter to only active substitutes with stock
    substitute_ids = [s.substitute_product_id for s in substitutes]
    if substitute_ids:
        stock_query = select(Inventory.product_id).where(
            Inventory.product_id.in_(substitute_ids),
            Inventory.quantity_available > 0
        ).distinct()
        stock_result = await db.execute(stock_query)
        in_stock_ids = {row[0] for row in stock_result.all()}
        substitutes = [s for s in substitutes if s.substitute_product_id in in_stock_ids]
    
    return substitutes


@router.post("/{product_id}/substitutes", response_model=ProductSubstituteResponse, status_code=status.HTTP_201_CREATED)
async def add_product_substitute(
    product_id: UUID,
    substitute_data: ProductSubstituteCreate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    if substitute_data.product_id != product_id:
        raise HTTPException(status_code=400, detail="Product ID mismatch")
    
    # Validate both products exist and belong to same distributor
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    if product.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = await db.execute(select(Product).where(Product.id == substitute_data.substitute_product_id))
    substitute_product = result.scalar_one_or_none()
    if not substitute_product:
        raise HTTPException(status_code=404, detail="Substitute product not found")
    
    if substitute_product.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Substitute product not from same distributor")
    
    # Check if already exists
    result = await db.execute(
        select(ProductSubstitute).where(
            ProductSubstitute.product_id == product_id,
            ProductSubstitute.substitute_product_id == substitute_data.substitute_product_id
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Substitute already exists")
    
    substitute = ProductSubstitute(**substitute_data.model_dump())
    db.add(substitute)
    await db.commit()
    await db.refresh(substitute)
    return substitute


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    update_data: ProductUpdate,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    if product.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check SKU uniqueness if changing
    if update_data.sku and update_data.sku != product.sku:
        result = await db.execute(
            select(Product).where(
                Product.distributor_id == current_user.distributor_id,
                Product.sku == update_data.sku
            )
        )
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="SKU already exists")
    
    # Check barcode uniqueness if changing
    if update_data.barcode and update_data.barcode != product.barcode:
        result = await db.execute(select(Product).where(Product.barcode == update_data.barcode))
        if result.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Barcode already exists")
    
    # Validate category if changing
    if update_data.category_id:
        result = await db.execute(select(ProductCategory).where(ProductCategory.id == update_data.category_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Category not found")
    
    # Validate manufacturer if changing
    if update_data.manufacturer_id:
        result = await db.execute(select(Manufacturer).where(Manufacturer.id == update_data.manufacturer_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Manufacturer not found")
    
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    
    if update_data.is_discontinued is True and not product.is_discontinued:
        product.discontinued_at = datetime.utcnow()
    
    await db.commit()
    return await get_product_with_details(product_id, db)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    if product.distributor_id != current_user.distributor_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    product.is_deleted = True
    product.deleted_at = datetime.utcnow()
    product.is_active = False
    await db.commit()