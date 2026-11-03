import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import (
    Column, String, Integer, BigInteger, DateTime, Date, Boolean,
    ForeignKey, UniqueConstraint, Index, CheckConstraint, Text,
    Numeric, Enum as SQLEnum, func, JSON
)
from sqlalchemy.orm import relationship, declared_attr
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.db.session import Base


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    DISTRIBUTOR_ADMIN = "distributor_admin"
    DISTRIBUTOR_STAFF = "distributor_staff"
    RETAILER_ADMIN = "retailer_admin"
    RETAILER_STAFF = "retailer_staff"


class UserStatus(str, enum.Enum):
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


class OrderStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED_BY_CREDIT = "approved_by_credit"
    PICKING = "picking"
    INVOICED = "invoiced"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    RETURN_REQUESTED = "return_requested"
    RETURN_APPROVED = "return_approved"
    RETURN_REJECTED = "return_rejected"
    CREDIT_NOTE_ISSUED = "credit_note_issued"


class ReturnReason(str, enum.Enum):
    BREAKAGE = "breakage"
    SPOILAGE = "spoilage"
    EXPIRED = "expired"
    WRONG_ITEM = "wrong_item"
    QUALITY_ISSUE = "quality_issue"
    EXCESS_STOCK = "excess_stock"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    GENERATED = "generated"
    E_INVOICE_PENDING = "e_invoice_pending"
    E_INVOICE_GENERATED = "e_invoice_generated"
    CANCELLED = "cancelled"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
    OVERDUE = "overdue"
    WRITE_OFF = "write_off"


class WarehouseType(str, enum.Enum):
    MAIN = "main"
    COLD_STORAGE = "cold_storage"
    INSTRUMENTS = "instruments"
    RETURN = "return"


class SchemeType(str, enum.Enum):
    BUY_GET_FREE = "buy_get_free"  # e.g., 10+1 free
    VOLUME_DISCOUNT = "volume_discount"  # percentage discount
    NET_RATE = "net_rate"  # custom net rate per retailer
    FLAT_DISCOUNT = "flat_discount"  # flat amount off


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SoftDeleteMixin:
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)


class BaseModel(Base, TimestampMixin, SoftDeleteMixin):
    __abstract__ = True
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Distributor(BaseModel):
    __tablename__ = "distributors"
    
    name = Column(String(255), nullable=False)
    legal_name = Column(String(255), nullable=False)
    gstin = Column(String(15), unique=True, nullable=False, index=True)
    pan = Column(String(10), nullable=False)
    address = Column(Text, nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    pincode = Column(String(6), nullable=False)
    phone = Column(String(15), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    drug_license_number = Column(String(50), unique=True, nullable=False, index=True)
    drug_license_form = Column(String(20), nullable=False)  # Form 20, Form 21
    drug_license_expiry = Column(Date, nullable=False)
    fssai_license = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    credit_limit = Column(Numeric(15, 2), default=0, nullable=False)
    payment_terms_days = Column(Integer, default=30, nullable=False)
    bank_details = Column(JSON, nullable=True)  # {account_name, account_number, ifsc, bank_name}
    
    # Relationships
    users = relationship("User", back_populates="distributor", foreign_keys="User.distributor_id")
    warehouses = relationship("Warehouse", back_populates="distributor")
    products = relationship("Product", back_populates="distributor")
    pricing_schemes = relationship("PricingScheme", back_populates="distributor")
    retailers = relationship("Retailer", back_populates="distributor")
    orders = relationship("Order", back_populates="distributor", foreign_keys="Order.distributor_id")
    invoices = relationship("Invoice", back_populates="distributor")
    
    __table_args__ = (
        CheckConstraint("char_length(gstin) = 15", name="valid_gstin_length"),
        Index("ix_distributors_gstin_active", "gstin", "is_active"),
    )


class Retailer(BaseModel):
    __tablename__ = "retailers"
    
    name = Column(String(255), nullable=False)
    legal_name = Column(String(255), nullable=False)
    gstin = Column(String(15), unique=True, nullable=False, index=True)
    pan = Column(String(10), nullable=False)
    address = Column(Text, nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    pincode = Column(String(6), nullable=False)
    phone = Column(String(15), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    drug_license_number = Column(String(50), unique=True, nullable=False, index=True)
    drug_license_form = Column(String(20), nullable=False)  # Form 20, Form 21
    drug_license_expiry = Column(Date, nullable=False)
    fssai_license = Column(String(50), nullable=True)
    retailer_type = Column(String(50), nullable=False)  # pharmacy, chemist, hospital, lab
    is_verified = Column(Boolean, default=False, nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    credit_limit = Column(Numeric(15, 2), default=0, nullable=False)
    used_credit = Column(Numeric(15, 2), default=0, nullable=False)
    payment_terms_days = Column(Integer, default=30, nullable=False)
    outstanding_balance = Column(Numeric(15, 2), default=0, nullable=False)
    overdue_days = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Distributor relationship (many-to-many via association table)
    distributor_id = Column(UUID(as_uuid=True), ForeignKey("distributors.id"), nullable=True)
    distributor = relationship("Distributor", back_populates="retailers")
    
    # Relationships
    users = relationship("User", back_populates="retailer", foreign_keys="User.retailer_id")
    orders = relationship("Order", back_populates="retailer")
    invoices = relationship("Invoice", back_populates="retailer")
    returns = relationship("ReturnRequest", back_populates="retailer")
    ledger_entries = relationship("LedgerEntry", back_populates="retailer")
    
    __table_args__ = (
        CheckConstraint("char_length(gstin) = 15", name="valid_retailer_gstin_length"),
        Index("ix_retailers_gstin_verified", "gstin", "is_verified"),
    )


class User(BaseModel):
    __tablename__ = "users"
    
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(15), nullable=True)
    role = Column(SQLEnum(UserRole), nullable=False, index=True)
    status = Column(SQLEnum(UserStatus), default=UserStatus.PENDING_VERIFICATION, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    
    # Foreign keys
    distributor_id = Column(UUID(as_uuid=True), ForeignKey("distributors.id"), nullable=True, index=True)
    retailer_id = Column(UUID(as_uuid=True), ForeignKey("retailers.id"), nullable=True, index=True)
    
    # Relationships
    distributor = relationship("Distributor", back_populates="users", foreign_keys=[distributor_id], remote_side=[Distributor.id])
    retailer = relationship("Retailer", back_populates="users", foreign_keys="User.retailer_id")
    verified_retailers = relationship("Retailer", foreign_keys=[Retailer.verified_by])
    created_orders = relationship("Order", back_populates="created_by_user", foreign_keys="Order.created_by")
    approved_orders = relationship("Order", back_populates="approved_by_user", foreign_keys="Order.approved_by")
    return_actions = relationship("ReturnRequest", back_populates="processed_by_user", foreign_keys="ReturnRequest.processed_by")
    notifications = relationship("Notification", foreign_keys="Notification.user_id")
    
    __table_args__ = (
        Index("ix_users_email_role", "email", "role"),
        Index("ix_users_distributor_role", "distributor_id", "role"),
        Index("ix_users_retailer_role", "retailer_id", "role"),
    )


class Warehouse(BaseModel):
    __tablename__ = "warehouses"
    
    name = Column(String(255), nullable=False)
    code = Column(String(20), nullable=False)
    warehouse_type = Column(SQLEnum(WarehouseType), default=WarehouseType.MAIN, nullable=False)
    address = Column(Text, nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    pincode = Column(String(6), nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    distributor_id = Column(UUID(as_uuid=True), ForeignKey("distributors.id"), nullable=False, index=True)
    distributor = relationship("Distributor", back_populates="warehouses")
    
    # Relationships
    inventory = relationship("Inventory", back_populates="warehouse")
    picking_slips = relationship("PickingSlip", back_populates="warehouse")
    
    __table_args__ = (
        UniqueConstraint("distributor_id", "code", name="uq_warehouse_distributor_code"),
        Index("ix_warehouses_distributor_active", "distributor_id", "is_active"),
    )


class ProductCategory(BaseModel):
    __tablename__ = "product_categories"
    
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("product_categories.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    
    # Self-referential
    parent = relationship("ProductCategory", foreign_keys=[parent_id], overlaps="children")
    children = relationship("ProductCategory", lazy="selectin", overlaps="parent")
    
    __table_args__ = (
        Index("ix_categories_parent_active", "parent_id", "is_active"),
    )


class Manufacturer(BaseModel):
    __tablename__ = "manufacturers"
    
    name = Column(String(255), nullable=False, unique=True, index=True)
    code = Column(String(50), nullable=False, unique=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    country = Column(String(100), default="India", nullable=False)
    gstin = Column(String(15), nullable=True)
    contact_person = Column(String(255), nullable=True)
    contact_phone = Column(String(15), nullable=True)
    contact_email = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    products = relationship("Product", back_populates="manufacturer")


class Product(BaseModel):
    __tablename__ = "products"
    
    # Core identification
    sku = Column(String(50), nullable=False, index=True)
    barcode = Column(String(50), unique=True, nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    generic_name = Column(String(255), nullable=False, index=True)  # Molecule/API name
    short_description = Column(String(500), nullable=True)
    long_description = Column(Text, nullable=True)
    
    # Classification
    category_id = Column(UUID(as_uuid=True), ForeignKey("product_categories.id"), nullable=False, index=True)
    manufacturer_id = Column(UUID(as_uuid=True), ForeignKey("manufacturers.id"), nullable=False, index=True)
    distributor_id = Column(UUID(as_uuid=True), ForeignKey("distributors.id"), nullable=False, index=True)
    
    # Regulatory
    hsn_code = Column(String(8), nullable=False, index=True)  # 4-8 digits
    drug_license_required = Column(Boolean, default=True, nullable=False)
    schedule = Column(String(20), nullable=True)  # Schedule H, H1, X, etc.
    is_prescription_required = Column(Boolean, default=False, nullable=False)
    
    # Physical attributes
    strength = Column(String(100), nullable=True)  # e.g., "500mg", "10ml"
    dosage_form = Column(String(50), nullable=True)  # tablet, capsule, syrup, injection, instrument
    pack_size = Column(String(50), nullable=False)  # e.g., "10x10", "100ml", "1 unit"
    unit_of_measure = Column(String(20), default="unit", nullable=False)  # unit, box, strip, bottle
    
    # Pricing
    mrp = Column(Numeric(10, 2), nullable=False)  # Maximum Retail Price
    trade_price = Column(Numeric(10, 2), nullable=False)  # Standard distributor price
    gst_rate = Column(Numeric(5, 2), default=12.00, nullable=False)  # GST %
    
    # Inventory control
    min_order_qty = Column(Integer, default=1, nullable=False)
    max_order_qty = Column(Integer, nullable=True)
    reorder_level = Column(Integer, default=10, nullable=False)
    is_cold_chain = Column(Boolean, default=False, nullable=False)
    is_instrument = Column(Boolean, default=False, nullable=False)
    instrument_specs = Column(JSON, nullable=True)  # For medical instruments
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_discontinued = Column(Boolean, default=False, nullable=False)
    discontinued_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    category = relationship("ProductCategory", backref="products")
    manufacturer = relationship("Manufacturer", back_populates="products")
    distributor = relationship("Distributor", back_populates="products")
    inventory = relationship("Inventory", back_populates="product")
    batches = relationship("ProductBatch", back_populates="product")
    order_items = relationship("OrderItem", back_populates="product")
    substitutes = relationship(
        "ProductSubstitute",
        foreign_keys="ProductSubstitute.product_id",
        back_populates="product"
    )
    substituted_by = relationship(
        "ProductSubstitute",
        foreign_keys="ProductSubstitute.substitute_product_id",
        back_populates="substitute_product"
    )
    
    __table_args__ = (
        UniqueConstraint("distributor_id", "sku", name="uq_product_distributor_sku"),
        CheckConstraint("char_length(hsn_code) BETWEEN 4 AND 8", name="valid_hsn_length"),
        CheckConstraint("mrp >= 0", name="positive_mrp"),
        CheckConstraint("trade_price >= 0", name="positive_trade_price"),
        CheckConstraint("gst_rate >= 0 AND gst_rate <= 28", name="valid_gst_rate"),
        Index("ix_products_search", "name", "generic_name", "sku"),
        Index("ix_products_distributor_active", "distributor_id", "is_active"),
    )


class ProductBatch(BaseModel):
    __tablename__ = "product_batches"
    
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    batch_number = Column(String(50), nullable=False, index=True)
    manufacture_date = Column(Date, nullable=False)
    expiry_date = Column(Date, nullable=False, index=True)
    mrp = Column(Numeric(10, 2), nullable=False)
    trade_price = Column(Numeric(10, 2), nullable=False)
    received_quantity = Column(Integer, default=0, nullable=False)
    available_quantity = Column(Integer, default=0, nullable=False)
    warehouse_id = Column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False, index=True)
    supplier_invoice_number = Column(String(100), nullable=True)
    supplier_invoice_date = Column(Date, nullable=True)
    cost_price = Column(Numeric(10, 2), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    product = relationship("Product", back_populates="batches")
    warehouse = relationship("Warehouse", backref="batches")
    inventory = relationship("Inventory", back_populates="batch")
    order_items = relationship("OrderItem", back_populates="batch")
    
    __table_args__ = (
        UniqueConstraint("product_id", "batch_number", "warehouse_id", name="uq_batch_product_warehouse"),
        CheckConstraint("expiry_date >= manufacture_date", name="valid_expiry_after_manufacture"),
        CheckConstraint("available_quantity <= received_quantity", name="valid_available_qty"),
        Index("ix_batches_expiry_warehouse", "expiry_date", "warehouse_id"),
        Index("ix_batches_product_expiry", "product_id", "expiry_date"),
    )


class Inventory(BaseModel):
    __tablename__ = "inventory"
    
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    batch_id = Column(UUID(as_uuid=True), ForeignKey("product_batches.id"), nullable=False, index=True)
    warehouse_id = Column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False, index=True)
    quantity_on_hand = Column(Integer, default=0, nullable=False)
    quantity_reserved = Column(Integer, default=0, nullable=False)  # Allocated to orders
    quantity_available = Column(Integer, default=0, nullable=False)  # on_hand - reserved
    last_stock_take = Column(DateTime(timezone=True), nullable=True)
    last_movement = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    product = relationship("Product", back_populates="inventory")
    batch = relationship("ProductBatch", back_populates="inventory")
    warehouse = relationship("Warehouse", back_populates="inventory")
    stock_movements = relationship("StockMovement", back_populates="inventory")
    
    __table_args__ = (
        UniqueConstraint("product_id", "batch_id", "warehouse_id", name="uq_inventory_product_batch_warehouse"),
        CheckConstraint("quantity_available = quantity_on_hand - quantity_reserved", name="valid_available_qty"),
        CheckConstraint("quantity_reserved >= 0", name="positive_reserved"),
        Index("ix_inventory_warehouse_product", "warehouse_id", "product_id"),
        Index("ix_inventory_available", "quantity_available"),
    )


class StockMovement(BaseModel):
    __tablename__ = "stock_movements"
    
    inventory_id = Column(UUID(as_uuid=True), ForeignKey("inventory.id"), nullable=False, index=True)
    movement_type = Column(String(20), nullable=False)  # in, out, transfer, adjustment, return
    quantity = Column(Integer, nullable=False)
    reference_type = Column(String(50), nullable=True)  # order, return, purchase, adjustment
    reference_id = Column(UUID(as_uuid=True), nullable=True)
    batch_number = Column(String(50), nullable=True)
    expiry_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    performed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    inventory = relationship("Inventory", back_populates="stock_movements")
    
    __table_args__ = (
        Index("ix_stock_movements_inventory_date", "inventory_id", "created_at"),
        Index("ix_stock_movements_reference", "reference_type", "reference_id"),
    )


class ProductSubstitute(BaseModel):
    __tablename__ = "product_substitutes"
    
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    substitute_product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    is_generic_equivalent = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=1, nullable=False)  # Lower = higher priority
    notes = Column(Text, nullable=True)
    
    product = relationship("Product", foreign_keys=[product_id], back_populates="substitutes")
    substitute_product = relationship("Product", foreign_keys=[substitute_product_id], back_populates="substituted_by")
    
    __table_args__ = (
        UniqueConstraint("product_id", "substitute_product_id", name="uq_product_substitute"),
        CheckConstraint("product_id != substitute_product_id", name="no_self_substitute"),
    )


class PricingScheme(BaseModel):
    __tablename__ = "pricing_schemes"
    
    distributor_id = Column(UUID(as_uuid=True), ForeignKey("distributors.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    scheme_type = Column(SQLEnum(SchemeType), nullable=False)
    scheme_config = Column(JSON, nullable=False)  # Type-specific config
    # For BUY_GET_FREE: {"buy_qty": 10, "free_qty": 1, "applicable_products": [product_ids]}
    # For VOLUME_DISCOUNT: {"tiers": [{"min_qty": 100, "discount_pct": 5}, {"min_qty": 500, "discount_pct": 10}]}
    # For NET_RATE: {"product_id": "...", "net_rate": 100.00}
    # For FLAT_DISCOUNT: {"min_order_value": 10000, "discount_amount": 500}
    
    applicable_product_ids = Column(JSON, nullable=True)  # List of product IDs, null = all
    applicable_category_ids = Column(JSON, nullable=True)  # List of category IDs
    applicable_retailer_ids = Column(JSON, nullable=True)  # List of retailer IDs, null = all
    min_order_value = Column(Numeric(15, 2), nullable=True)
    max_discount_per_order = Column(Numeric(15, 2), nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=0, nullable=False)  # Higher = applied first
    
    distributor = relationship("Distributor", back_populates="pricing_schemes")
    
    __table_args__ = (
        Index("ix_pricing_schemes_distributor_active", "distributor_id", "is_active"),
        Index("ix_pricing_schemes_dates", "start_date", "end_date"),
    )


class Order(BaseModel):
    __tablename__ = "orders"
    
    order_number = Column(String(50), unique=True, nullable=False, index=True)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.DRAFT, nullable=False, index=True)
    
    # Parties
    distributor_id = Column(UUID(as_uuid=True), ForeignKey("distributors.id"), nullable=False, index=True)
    retailer_id = Column(UUID(as_uuid=True), ForeignKey("retailers.id"), nullable=False, index=True)
    warehouse_id = Column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=True)
    
    # Users
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    # Financial
    subtotal = Column(Numeric(15, 2), default=0, nullable=False)
    discount_amount = Column(Numeric(15, 2), default=0, nullable=False)
    tax_amount = Column(Numeric(15, 2), default=0, nullable=False)
    total_amount = Column(Numeric(15, 2), default=0, nullable=False)
    
    # Credit check
    credit_checked = Column(Boolean, default=False, nullable=False)
    credit_check_passed = Column(Boolean, default=False, nullable=False)
    credit_check_notes = Column(Text, nullable=True)
    credit_checked_at = Column(DateTime(timezone=True), nullable=True)
    credit_checked_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    # Dates
    order_date = Column(Date, nullable=False, default=func.current_date())
    expected_delivery_date = Column(Date, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    invoiced_at = Column(DateTime(timezone=True), nullable=True)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Shipping
    shipping_address = Column(Text, nullable=True)
    shipping_city = Column(String(100), nullable=True)
    shipping_state = Column(String(100), nullable=True)
    shipping_pincode = Column(String(6), nullable=True)
    shipping_contact_name = Column(String(255), nullable=True)
    shipping_contact_phone = Column(String(15), nullable=True)
    
    # Notes
    retailer_notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    
    # Relationships
    distributor = relationship("Distributor", back_populates="orders", foreign_keys=[distributor_id])
    retailer = relationship("Retailer", back_populates="orders")
    warehouse = relationship("Warehouse", backref="orders")
    created_by_user = relationship("User", foreign_keys=[created_by], back_populates="created_orders")
    approved_by_user = relationship("User", foreign_keys=[approved_by], back_populates="approved_orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="order")
    picking_slips = relationship("PickingSlip", back_populates="order")
    status_history = relationship("OrderStatusHistory", back_populates="order", cascade="all, delete-orphan")
    eway_bill = relationship("EWayBill", back_populates="order", uselist=False)
    
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="positive_total"),
        CheckConstraint("subtotal >= 0", name="positive_subtotal"),
        Index("ix_orders_distributor_status_date", "distributor_id", "status", "order_date"),
        Index("ix_orders_retailer_status_date", "retailer_id", "status", "order_date"),
        Index("ix_orders_status_date", "status", "order_date"),
    )


class OrderItem(BaseModel):
    __tablename__ = "order_items"
    
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    batch_id = Column(UUID(as_uuid=True), ForeignKey("product_batches.id"), nullable=True, index=True)
    
    # Snapshot of product data at order time
    product_name = Column(String(255), nullable=False)
    product_sku = Column(String(50), nullable=False)
    product_generic_name = Column(String(255), nullable=False)
    batch_number = Column(String(50), nullable=True)
    expiry_date = Column(Date, nullable=True)
    hsn_code = Column(String(8), nullable=False)
    gst_rate = Column(Numeric(5, 2), nullable=False)
    unit_of_measure = Column(String(20), nullable=False)
    pack_size = Column(String(50), nullable=False)
    
    # Quantities
    ordered_qty = Column(Integer, nullable=False)
    packed_qty = Column(Integer, default=0, nullable=False)
    delivered_qty = Column(Integer, default=0, nullable=False)
    returned_qty = Column(Integer, default=0, nullable=False)
    
    # Pricing
    unit_price = Column(Numeric(10, 2), nullable=False)  # Price per unit after scheme
    mrp = Column(Numeric(10, 2), nullable=False)
    discount_per_unit = Column(Numeric(10, 2), default=0, nullable=False)
    scheme_applied = Column(JSON, nullable=True)  # Scheme details applied
    
    # Calculated
    line_subtotal = Column(Numeric(15, 2), nullable=False)
    line_discount = Column(Numeric(15, 2), default=0, nullable=False)
    line_tax = Column(Numeric(15, 2), nullable=False)
    line_total = Column(Numeric(15, 2), nullable=False)
    
    # Status
    is_packed = Column(Boolean, default=False, nullable=False)
    is_invoiced = Column(Boolean, default=False, nullable=False)
    is_dispatched = Column(Boolean, default=False, nullable=False)
    
    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")
    batch = relationship("ProductBatch", back_populates="order_items")
    
    __table_args__ = (
        CheckConstraint("ordered_qty > 0", name="positive_ordered_qty"),
        CheckConstraint("packed_qty <= ordered_qty", name="valid_packed_qty"),
        CheckConstraint("delivered_qty <= packed_qty", name="valid_delivered_qty"),
        CheckConstraint("returned_qty <= delivered_qty", name="valid_returned_qty"),
        CheckConstraint("unit_price >= 0", name="positive_unit_price"),
        Index("ix_order_items_order_product", "order_id", "product_id"),
    )


class PickingSlip(BaseModel):
    __tablename__ = "picking_slips"
    
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True)
    warehouse_id = Column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False, index=True)
    slip_number = Column(String(50), unique=True, nullable=False, index=True)
    status = Column(String(20), default="picking", nullable=False)  # picking, completed
    
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    packed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    packed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    order = relationship("Order", back_populates="picking_slips")
    warehouse = relationship("Warehouse", back_populates="picking_slips")
    created_by_user = relationship("User", foreign_keys=[created_by])
    packed_by_user = relationship("User", foreign_keys=[packed_by])
    items = relationship("PickingSlipItem", back_populates="picking_slip", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_picking_slips_order_warehouse", "order_id", "warehouse_id"),
    )


class PickingSlipItem(BaseModel):
    __tablename__ = "picking_slip_items"
    
    picking_slip_id = Column(UUID(as_uuid=True), ForeignKey("picking_slips.id"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    batch_id = Column(UUID(as_uuid=True), ForeignKey("product_batches.id"), nullable=False, index=True)
    
    product_name = Column(String(255), nullable=False)
    product_sku = Column(String(50), nullable=False)
    batch_number = Column(String(50), nullable=False)
    expiry_date = Column(Date, nullable=False)
    quantity = Column(Integer, nullable=False)
    warehouse_location = Column(String(100), nullable=True)
    is_instrument = Column(Boolean, default=False, nullable=False)
    instrument_check_required = Column(Boolean, default=False, nullable=False)
    instrument_check_passed = Column(Boolean, nullable=True)
    
    # Relationships
    picking_slip = relationship("PickingSlip", back_populates="items")
    product = relationship("Product")
    batch = relationship("ProductBatch")
    
    __table_args__ = (
        Index("ix_picking_slip_items_slip_product", "picking_slip_id", "product_id"),
    )


class OrderStatusHistory(BaseModel):
    __tablename__ = "order_status_history"
    
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True)
    from_status = Column(SQLEnum(OrderStatus), nullable=True)
    to_status = Column(SQLEnum(OrderStatus), nullable=False)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    meta = Column(JSON, nullable=True)  # Additional context
    
    order = relationship("Order", back_populates="status_history")
    changed_by_user = relationship("User", foreign_keys=[changed_by])
    
    __table_args__ = (
        Index("ix_order_status_history_order_date", "order_id", "created_at"),
    )


class Invoice(BaseModel):
    __tablename__ = "invoices"
    
    invoice_number = Column(String(50), unique=True, nullable=False, index=True)
    invoice_series = Column(String(10), nullable=False)  # e.g., "B2B", "B2C", "EXP"
    status = Column(SQLEnum(InvoiceStatus), default=InvoiceStatus.DRAFT, nullable=False, index=True)
    
    # Parties
    distributor_id = Column(UUID(as_uuid=True), ForeignKey("distributors.id"), nullable=False, index=True)
    retailer_id = Column(UUID(as_uuid=True), ForeignKey("retailers.id"), nullable=False, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True)
    
    # Financial
    taxable_value = Column(Numeric(15, 2), default=0, nullable=False)
    cgst_amount = Column(Numeric(15, 2), default=0, nullable=False)
    sgst_amount = Column(Numeric(15, 2), default=0, nullable=False)
    igst_amount = Column(Numeric(15, 2), default=0, nullable=False)
    total_tax = Column(Numeric(15, 2), default=0, nullable=False)
    total_amount = Column(Numeric(15, 2), default=0, nullable=False)
    round_off = Column(Numeric(15, 2), default=0, nullable=False)
    
    # GST Details
    place_of_supply = Column(String(100), nullable=False)
    supply_type = Column(String(20), nullable=False)  # inter_state, intra_state
    reverse_charge = Column(Boolean, default=False, nullable=False)
    
    # E-Invoice
    irn = Column(String(100), unique=True, nullable=True, index=True)  # Invoice Reference Number
    ack_no = Column(String(100), nullable=True)
    ack_date = Column(DateTime(timezone=True), nullable=True)
    signed_invoice = Column(Text, nullable=True)
    qr_code = Column(Text, nullable=True)
    e_invoice_errors = Column(JSON, nullable=True)
    
    # Dates
    invoice_date = Column(Date, nullable=False, default=func.current_date())
    due_date = Column(Date, nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=True)
    
    # Payment
    payment_status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    paid_amount = Column(Numeric(15, 2), default=0, nullable=False)
    balance_amount = Column(Numeric(15, 2), default=0, nullable=False)
    
    # Relationships
    distributor = relationship("Distributor", back_populates="invoices")
    retailer = relationship("Retailer", back_populates="invoices")
    order = relationship("Order", back_populates="invoices")
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="invoice")
    credit_notes = relationship("CreditNote", back_populates="invoice")
    eway_bill = relationship("EWayBill", back_populates="invoice", uselist=False)
    
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="positive_invoice_total"),
        CheckConstraint("balance_amount = total_amount - paid_amount", name="valid_balance"),
        Index("ix_invoices_distributor_date_status", "distributor_id", "invoice_date", "status"),
        Index("ix_invoices_retailer_date_status", "retailer_id", "invoice_date", "status"),
        Index("ix_invoices_due_payment", "due_date", "payment_status"),
    )


class InvoiceItem(BaseModel):
    __tablename__ = "invoice_items"
    
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    order_item_id = Column(UUID(as_uuid=True), ForeignKey("order_items.id"), nullable=True)
    
    # Snapshot
    product_name = Column(String(255), nullable=False)
    product_sku = Column(String(50), nullable=False)
    hsn_code = Column(String(8), nullable=False)
    batch_number = Column(String(50), nullable=True)
    expiry_date = Column(Date, nullable=True)
    unit_of_measure = Column(String(20), nullable=False)
    pack_size = Column(String(50), nullable=False)
    
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    discount = Column(Numeric(10, 2), default=0, nullable=False)
    taxable_value = Column(Numeric(15, 2), nullable=False)
    gst_rate = Column(Numeric(5, 2), nullable=False)
    cgst_rate = Column(Numeric(5, 2), default=0, nullable=False)
    sgst_rate = Column(Numeric(5, 2), default=0, nullable=False)
    igst_rate = Column(Numeric(5, 2), default=0, nullable=False)
    cgst_amount = Column(Numeric(15, 2), default=0, nullable=False)
    sgst_amount = Column(Numeric(15, 2), default=0, nullable=False)
    igst_amount = Column(Numeric(15, 2), default=0, nullable=False)
    total_amount = Column(Numeric(15, 2), nullable=False)
    
    invoice = relationship("Invoice", back_populates="items")
    
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_inv_qty"),
        CheckConstraint("unit_price >= 0", name="positive_inv_unit_price"),
    )


class Payment(BaseModel):
    __tablename__ = "payments"
    
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    payment_number = Column(String(50), unique=True, nullable=False, index=True)
    amount = Column(Numeric(15, 2), nullable=False)
    payment_mode = Column(String(20), nullable=False)  # cash, cheque, neft, rtgs, upi, bank_transfer
    reference_number = Column(String(100), nullable=True)
    payment_date = Column(Date, nullable=False)
    received_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    bank_name = Column(String(100), nullable=True)
    cheque_date = Column(Date, nullable=True)
    clearance_date = Column(Date, nullable=True)
    is_reconciled = Column(Boolean, default=False, nullable=False)
    
    invoice = relationship("Invoice", back_populates="payments")
    received_by_user = relationship("User", foreign_keys=[received_by])
    
    __table_args__ = (
        CheckConstraint("amount > 0", name="positive_payment"),
        Index("ix_payments_invoice_date", "invoice_id", "payment_date"),
        Index("ix_payments_mode_date", "payment_mode", "payment_date"),
    )


class CreditNote(BaseModel):
    __tablename__ = "credit_notes"
    
    credit_note_number = Column(String(50), unique=True, nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    return_request_id = Column(UUID(as_uuid=True), ForeignKey("return_requests.id"), nullable=True, index=True)
    
    reason = Column(Text, nullable=False)
    taxable_value = Column(Numeric(15, 2), default=0, nullable=False)
    cgst_amount = Column(Numeric(15, 2), default=0, nullable=False)
    sgst_amount = Column(Numeric(15, 2), default=0, nullable=False)
    igst_amount = Column(Numeric(15, 2), default=0, nullable=False)
    total_amount = Column(Numeric(15, 2), default=0, nullable=False)
    
    # GST
    place_of_supply = Column(String(100), nullable=False)
    supply_type = Column(String(20), nullable=False)
    
    status = Column(String(20), default="draft", nullable=False)  # draft, issued, cancelled
    issued_at = Column(DateTime(timezone=True), nullable=True)
    issued_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    # E-Invoice for Credit Note
    irn = Column(String(100), unique=True, nullable=True, index=True)
    
    invoice = relationship("Invoice", back_populates="credit_notes")
    return_request = relationship("ReturnRequest", back_populates="credit_note")
    items = relationship("CreditNoteItem", back_populates="credit_note", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="positive_cn_total"),
    )


class CreditNoteItem(BaseModel):
    __tablename__ = "credit_note_items"
    
    credit_note_id = Column(UUID(as_uuid=True), ForeignKey("credit_notes.id"), nullable=False, index=True)
    invoice_item_id = Column(UUID(as_uuid=True), ForeignKey("invoice_items.id"), nullable=True)
    
    product_name = Column(String(255), nullable=False)
    hsn_code = Column(String(8), nullable=False)
    batch_number = Column(String(50), nullable=True)
    expiry_date = Column(Date, nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    taxable_value = Column(Numeric(15, 2), nullable=False)
    gst_rate = Column(Numeric(5, 2), nullable=False)
    total_amount = Column(Numeric(15, 2), nullable=False)
    
    credit_note = relationship("CreditNote", back_populates="items")
    
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_cn_qty"),
    )


class ReturnRequest(BaseModel):
    __tablename__ = "return_requests"
    
    return_number = Column(String(50), unique=True, nullable=False, index=True)
    retailer_id = Column(UUID(as_uuid=True), ForeignKey("retailers.id"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True, index=True)
    
    reason = Column(SQLEnum(ReturnReason), nullable=False)
    reason_description = Column(Text, nullable=True)
    status = Column(String(20), default="pending", nullable=False)  # pending, approved, rejected, received, credit_note_issued
    
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    processed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    processor_notes = Column(Text, nullable=True)
    
    # Quality check for instruments
    requires_inspection = Column(Boolean, default=False, nullable=False)
    inspection_passed = Column(Boolean, nullable=True)
    inspection_notes = Column(Text, nullable=True)
    inspected_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    inspected_at = Column(DateTime(timezone=True), nullable=True)
    
    # Dates
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    retailer = relationship("Retailer", back_populates="returns")
    invoice = relationship("Invoice", backref="return_requests")
    order = relationship("Order", backref="return_requests")
    requested_by_user = relationship("User", foreign_keys=[requested_by])
    processed_by_user = relationship("User", foreign_keys=[processed_by], back_populates="return_actions")
    inspected_by_user = relationship("User", foreign_keys=[inspected_by])
    items = relationship("ReturnRequestItem", back_populates="return_request", cascade="all, delete-orphan")
    credit_note = relationship("CreditNote", back_populates="return_request", uselist=False)
    
    __table_args__ = (
        Index("ix_returns_retailer_status", "retailer_id", "status"),
        Index("ix_returns_invoice_status", "invoice_id", "status"),
    )


class ReturnRequestItem(BaseModel):
    __tablename__ = "return_request_items"
    
    return_request_id = Column(UUID(as_uuid=True), ForeignKey("return_requests.id"), nullable=False, index=True)
    invoice_item_id = Column(UUID(as_uuid=True), ForeignKey("invoice_items.id"), nullable=False)
    order_item_id = Column(UUID(as_uuid=True), ForeignKey("order_items.id"), nullable=True)
    
    product_name = Column(String(255), nullable=False)
    batch_number = Column(String(50), nullable=True)
    expiry_date = Column(Date, nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total_amount = Column(Numeric(15, 2), nullable=False)
    
    # Approval
    approved_quantity = Column(Integer, default=0, nullable=False)
    rejected_quantity = Column(Integer, default=0, nullable=False)
    rejection_reason = Column(Text, nullable=True)
    
    return_request = relationship("ReturnRequest", back_populates="items")
    
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_rr_qty"),
        CheckConstraint("approved_quantity + rejected_quantity <= quantity", name="valid_approved_rejected"),
    )


class EWayBill(BaseModel):
    __tablename__ = "eway_bills"
    
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True, unique=True, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True, unique=True, index=True)
    
    eway_bill_number = Column(String(50), unique=True, nullable=True, index=True)
    eway_bill_date = Column(DateTime(timezone=True), nullable=True)
    valid_upto = Column(DateTime(timezone=True), nullable=True)
    
    # Part A
    gstin_supplier = Column(String(15), nullable=False)
    gstin_recipient = Column(String(15), nullable=False)
    place_of_dispatch = Column(String(100), nullable=False)
    place_of_delivery = Column(String(100), nullable=False)
    document_type = Column(String(20), nullable=False)  # INV, CN, DN
    document_number = Column(String(50), nullable=False)
    document_date = Column(Date, nullable=False)
    transaction_type = Column(String(20), nullable=False)  # Regular, Bill To Ship To
    value_of_goods = Column(Numeric(15, 2), nullable=False)
    hsn_codes = Column(JSON, nullable=False)  # List of HSN codes
    reason_for_transportation = Column(String(50), nullable=False)
    
    # Part B - Transporter
    transporter_id = Column(String(15), nullable=True)
    transporter_name = Column(String(255), nullable=True)
    vehicle_number = Column(String(20), nullable=True)
    transport_mode = Column(String(20), nullable=True)  # Road, Rail, Air, Ship
    transport_doc_number = Column(String(50), nullable=True)
    transport_doc_date = Column(Date, nullable=True)
    distance = Column(Integer, nullable=True)  # km
    
    # Status
    status = Column(String(20), default="draft", nullable=False)  # draft, generated, cancelled, expired
    error_message = Column(Text, nullable=True)
    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    
    order = relationship("Order", back_populates="eway_bill")
    invoice = relationship("Invoice", back_populates="eway_bill")
    
    __table_args__ = (
        Index("ix_eway_bills_status_date", "status", "eway_bill_date"),
        Index("ix_eway_bills_supplier_recipient", "gstin_supplier", "gstin_recipient"),
    )


class LedgerEntry(BaseModel):
    __tablename__ = "ledger_entries"
    
    retailer_id = Column(UUID(as_uuid=True), ForeignKey("retailers.id"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True, index=True)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=True, index=True)
    credit_note_id = Column(UUID(as_uuid=True), ForeignKey("credit_notes.id"), nullable=True, index=True)
    
    entry_type = Column(String(20), nullable=False)  # invoice, payment, credit_note, debit_note, adjustment
    description = Column(Text, nullable=False)
    debit_amount = Column(Numeric(15, 2), default=0, nullable=False)
    credit_amount = Column(Numeric(15, 2), default=0, nullable=False)
    balance = Column(Numeric(15, 2), nullable=False)  # Running balance
    entry_date = Column(Date, nullable=False)
    reference_number = Column(String(50), nullable=True)
    
    retailer = relationship("Retailer", back_populates="ledger_entries")
    
    __table_args__ = (
        CheckConstraint("debit_amount >= 0 AND credit_amount >= 0", name="positive_amounts"),
        CheckConstraint("NOT (debit_amount > 0 AND credit_amount > 0)", name="one_direction"),
        Index("ix_ledger_retailer_date", "retailer_id", "entry_date"),
        Index("ix_ledger_reference", "reference_number"),
    )


class AuditLog(BaseModel):
    __tablename__ = "audit_logs"
    
    entity_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    action = Column(String(50), nullable=False)  # create, update, delete, status_change
    old_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=True)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_user_date", "changed_by", "created_at"),
    )


class Notification(BaseModel):
    __tablename__ = "notifications"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), nullable=False)  # order, payment, return, credit_limit, stock, system
    reference_type = Column(String(50), nullable=True)
    reference_id = Column(UUID(as_uuid=True), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    action_url = Column(String(500), nullable=True)
    
    user = relationship("User", foreign_keys=[user_id])
    
    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "is_read"),
        Index("ix_notifications_type_ref", "reference_type", "reference_id"),
    )