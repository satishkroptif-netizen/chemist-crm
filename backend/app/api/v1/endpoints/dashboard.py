from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, case
from sqlalchemy.orm import selectinload, joinedload
from uuid import UUID
from typing import Optional, List
from decimal import Decimal
from datetime import date, datetime, timedelta
from app.db.session import get_db
from app.core.security import get_current_active_user, require_distributor_access, require_retailer_access
from app.models import (
    Retailer, Order, OrderStatus, Invoice, InvoiceStatus, PaymentStatus,
    Product, ProductBatch, Inventory, ReturnRequest, Warehouse,
    User, UserRole, Distributor
)
from app.schemas import DistributorDashboardStats, RetailerDashboardStats
from app.core.config import get_settings

router = APIRouter()

settings = get_settings()


@router.get("/distributor", response_model=DistributorDashboardStats)
async def distributor_dashboard(
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    if not distributor_id:
        raise HTTPException(status_code=403, detail="User not associated with a distributor")
    
    today = date.today()
    start_of_month = today.replace(day=1)
    
    # Total retailers
    total_retailers = await db.scalar(
        select(func.count(Retailer.id)).where(Retailer.distributor_id == distributor_id)
    )
    
    # Active retailers
    active_retailers = await db.scalar(
        select(func.count(Retailer.id)).where(
            Retailer.distributor_id == distributor_id,
            Retailer.is_active == True,
            Retailer.is_verified == True
        )
    )
    
    # Pending verification
    pending_verification = await db.scalar(
        select(func.count(Retailer.id)).where(
            Retailer.distributor_id == distributor_id,
            Retailer.is_verified == False
        )
    )
    
    # Orders today
    total_orders_today = await db.scalar(
        select(func.count(Order.id)).where(
            Order.distributor_id == distributor_id,
            Order.order_date == today
        )
    )
    
    # Orders this month
    total_orders_this_month = await db.scalar(
        select(func.count(Order.id)).where(
            Order.distributor_id == distributor_id,
            Order.order_date >= start_of_month
        )
    )
    
    # Revenue today
    revenue_today = await db.scalar(
        select(func.sum(Invoice.total_amount)).where(
            Invoice.distributor_id == distributor_id,
            Invoice.invoice_date == today,
            Invoice.status != InvoiceStatus.CANCELLED
        )
    ) or Decimal("0")
    
    # Revenue this month
    revenue_this_month = await db.scalar(
        select(func.sum(Invoice.total_amount)).where(
            Invoice.distributor_id == distributor_id,
            Invoice.invoice_date >= start_of_month,
            Invoice.status != InvoiceStatus.CANCELLED
        )
    ) or Decimal("0")
    
    # Outstanding receivables
    outstanding_receivables = await db.scalar(
        select(func.sum(Retailer.outstanding_balance)).where(
            Retailer.distributor_id == distributor_id,
            Retailer.is_active == True
        )
    ) or Decimal("0")
    
    # Overdue receivables
    overdue_receivables = await db.scalar(
        select(func.sum(Invoice.balance_amount)).where(
            Invoice.distributor_id == distributor_id,
            Invoice.payment_status.in_(["pending", "partial", "overdue"]),
            Invoice.due_date < today
        )
    ) or Decimal("0")
    
    # Low stock products
    low_stock_products = await db.scalar(
        select(func.count(func.distinct(Product.id))).join(Inventory).where(
            Product.distributor_id == distributor_id,
            Product.is_active == True,
            Inventory.quantity_available > 0,
            Inventory.quantity_available <= Product.reorder_level
        )
    ) or 0
    
    # Expiring soon products
    threshold_date = today + timedelta(days=settings.EXPIRY_WARNING_DAYS)
    expiring_soon = await db.scalar(
        select(func.count(func.distinct(Product.id))).join(ProductBatch).join(Inventory).where(
            Product.distributor_id == distributor_id,
            Product.is_active == True,
            ProductBatch.is_active == True,
            ProductBatch.expiry_date <= threshold_date,
            ProductBatch.expiry_date >= today,
            Inventory.quantity_available > 0
        )
    ) or 0
    
    # Pending returns
    pending_returns = await db.scalar(
        select(func.count(ReturnRequest.id)).join(Invoice).where(
            Invoice.distributor_id == distributor_id,
            ReturnRequest.status == "pending"
        )
    ) or 0
    
    return DistributorDashboardStats(
        total_retailers=total_retailers or 0,
        active_retailers=active_retailers or 0,
        pending_verification=pending_verification or 0,
        total_orders_today=total_orders_today or 0,
        total_orders_this_month=total_orders_this_month or 0,
        revenue_today=revenue_today,
        revenue_this_month=revenue_this_month,
        outstanding_receivables=outstanding_receivables,
        overdue_receivables=overdue_receivables,
        low_stock_products=low_stock_products,
        expiring_soon_products=expiring_soon,
        pending_returns=pending_returns
    )


@router.get("/retailer", response_model=RetailerDashboardStats)
async def retailer_dashboard(
    current_user: User = Depends(require_retailer_access),
    db: AsyncSession = Depends(get_db)
):
    retailer_id = current_user.retailer_id
    if not retailer_id:
        raise HTTPException(status_code=403, detail="User not associated with a retailer")
    
    # Get retailer
    retailer_result = await db.execute(
        select(Retailer).where(Retailer.id == retailer_id)
    )
    retailer = retailer_result.scalar_one()
    
    # Order counts
    my_orders_count = await db.scalar(
        select(func.count(Order.id)).where(Order.retailer_id == retailer_id)
    ) or 0
    
    pending_orders = await db.scalar(
        select(func.count(Order.id)).where(
            Order.retailer_id == retailer_id,
            Order.status.in_([OrderStatus.DRAFT, OrderStatus.SUBMITTED, OrderStatus.APPROVED_BY_CREDIT, OrderStatus.PICKING, OrderStatus.INVOICED, OrderStatus.DISPATCHED])
        )
    ) or 0
    
    delivered_orders = await db.scalar(
        select(func.count(Order.id)).where(
            Order.retailer_id == retailer_id,
            Order.status.in_([OrderStatus.DELIVERED, OrderStatus.CLOSED])
        )
    ) or 0
    
    # Recent invoices
    recent_invoices_result = await db.execute(
        select(Invoice).options(joinedload(Invoice.items))
        .where(Invoice.retailer_id == retailer_id)
        .order_by(Invoice.invoice_date.desc())
        .limit(5)
    )
    recent_invoices = recent_invoices_result.scalars().all()
    
    # Recent orders
    recent_orders_result = await db.execute(
        select(Order).options(joinedload(Order.items))
        .where(Order.retailer_id == retailer_id)
        .order_by(Order.created_at.desc())
        .limit(5)
    )
    recent_orders = recent_orders_result.scalars().all()
    
    return RetailerDashboardStats(
        my_orders_count=my_orders_count,
        pending_orders=pending_orders,
        delivered_orders=delivered_orders,
        outstanding_balance=retailer.outstanding_balance,
        credit_limit=retailer.credit_limit,
        available_credit=max(retailer.credit_limit - retailer.outstanding_balance, Decimal("0")),
        overdue_amount=retailer.outstanding_balance if retailer.overdue_days > 0 else Decimal("0"),
        overdue_days=retailer.overdue_days,
        recent_invoices=recent_invoices,
        recent_orders=recent_orders
    )


@router.get("/sales-summary")
async def sales_summary(
    date_from: date,
    date_to: date,
    group_by: str = Query("day", pattern="^(day|week|month)$"),
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    
    # Determine date truncation
    if group_by == "day":
        date_trunc = func.date(Invoice.invoice_date)
    elif group_by == "week":
        date_trunc = func.date_trunc('week', Invoice.invoice_date)
    else:
        date_trunc = func.date_trunc('month', Invoice.invoice_date)
    
    query = select(
        date_trunc.label("period"),
        func.count(Invoice.id).label("invoice_count"),
        func.sum(Invoice.total_amount).label("total_revenue"),
        func.sum(Invoice.taxable_value).label("taxable_value"),
        func.sum(Invoice.total_tax).label("total_tax")
    ).where(
        Invoice.distributor_id == distributor_id,
        Invoice.invoice_date >= date_from,
        Invoice.invoice_date <= date_to,
        Invoice.status != InvoiceStatus.CANCELLED
    ).group_by(date_trunc).order_by(date_trunc)
    
    result = await db.execute(query)
    return [
        {
            "period": row.period.isoformat() if row.period else None,
            "invoice_count": row.invoice_count,
            "total_revenue": float(row.total_revenue or 0),
            "taxable_value": float(row.taxable_value or 0),
            "total_tax": float(row.total_tax or 0)
        }
        for row in result.all()
    ]


@router.get("/top-products")
async def top_products(
    date_from: date,
    date_to: date,
    limit: int = 10,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    
    query = select(
        Product.name,
        Product.sku,
        func.sum(OrderItem.ordered_qty).label("total_qty"),
        func.sum(OrderItem.line_total).label("total_revenue")
    ).join(OrderItem).join(Order).join(Invoice).where(
        Invoice.distributor_id == distributor_id,
        Invoice.invoice_date >= date_from,
        Invoice.invoice_date <= date_to,
        Invoice.status != InvoiceStatus.CANCELLED
    ).group_by(Product.id, Product.name, Product.sku).order_by(
        func.sum(OrderItem.line_total).desc()
    ).limit(limit)
    
    result = await db.execute(query)
    return [
        {
            "product_name": row.name,
            "sku": row.sku,
            "total_quantity": row.total_qty,
            "total_revenue": float(row.total_revenue or 0)
        }
        for row in result.all()
    ]


@router.get("/top-retailers")
async def top_retailers(
    date_from: date,
    date_to: date,
    limit: int = 10,
    current_user: User = Depends(require_distributor_access),
    db: AsyncSession = Depends(get_db)
):
    distributor_id = current_user.distributor_id
    
    query = select(
        Retailer.name,
        Retailer.gstin,
        func.count(Invoice.id).label("invoice_count"),
        func.sum(Invoice.total_amount).label("total_revenue"),
        Retailer.outstanding_balance
    ).join(Invoice).where(
        Invoice.distributor_id == distributor_id,
        Invoice.invoice_date >= date_from,
        Invoice.invoice_date <= date_to,
        Invoice.status != InvoiceStatus.CANCELLED
    ).group_by(Retailer.id, Retailer.name, Retailer.gstin, Retailer.outstanding_balance).order_by(
        func.sum(Invoice.total_amount).desc()
    ).limit(limit)
    
    result = await db.execute(query)
    return [
        {
            "retailer_name": row.name,
            "gstin": row.gstin,
            "invoice_count": row.invoice_count,
            "total_revenue": float(row.total_revenue or 0),
            "outstanding_balance": float(row.outstanding_balance or 0)
        }
        for row in result.all()
    ]