from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth, users, distributors, retailers, warehouses,
    categories, manufacturers, products, batches, inventory,
    pricing_schemes, orders, invoices, payments, credit_notes,
    returns, eway_bills, ledger, dashboard, picking
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(distributors.router, prefix="/distributors", tags=["Distributors"])
api_router.include_router(retailers.router, prefix="/retailers", tags=["Retailers"])
api_router.include_router(warehouses.router, prefix="/warehouses", tags=["Warehouses"])
api_router.include_router(categories.router, prefix="/categories", tags=["Categories"])
api_router.include_router(manufacturers.router, prefix="/manufacturers", tags=["Manufacturers"])
api_router.include_router(products.router, prefix="/products", tags=["Products"])
api_router.include_router(batches.router, prefix="/batches", tags=["Batches"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["Inventory"])
api_router.include_router(pricing_schemes.router, prefix="/pricing-schemes", tags=["Pricing Schemes"])
api_router.include_router(orders.router, prefix="/orders", tags=["Orders"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["Invoices"])
api_router.include_router(payments.router, prefix="/payments", tags=["Payments"])
api_router.include_router(credit_notes.router, prefix="/credit-notes", tags=["Credit Notes"])
api_router.include_router(returns.router, prefix="/returns", tags=["Returns"])
api_router.include_router(eway_bills.router, prefix="/eway-bills", tags=["E-Way Bills"])
api_router.include_router(ledger.router, prefix="/ledger", tags=["Ledger"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(picking.router, prefix="/picking", tags=["Picking"])