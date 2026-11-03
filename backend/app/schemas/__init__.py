from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID
import re

from app.models import (
    UserRole, UserStatus, OrderStatus, ReturnReason, InvoiceStatus,
    PaymentStatus, WarehouseType, SchemeType
)


# ============ Base Schemas ============

class TimestampMixin(BaseModel):
    created_at: datetime
    updated_at: datetime


class IDMixin(BaseModel):
    id: UUID


# ============ Auth Schemas ============

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    sub: UUID
    email: EmailStr
    role: UserRole
    distributor_id: Optional[UUID] = None
    retailer_id: Optional[UUID] = None
    exp: int
    type: str = "access"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
    
    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v


# ============ User Schemas ============

class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=255)
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")
    role: UserRole
    distributor_id: Optional[UUID] = None
    retailer_id: Optional[UUID] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")
    is_active: Optional[bool] = None
    avatar_url: Optional[str] = Field(None, max_length=500)


class UserResponse(UserBase, IDMixin, TimestampMixin):
    status: UserStatus
    is_active: bool
    last_login: Optional[datetime] = None
    avatar_url: Optional[str] = None
    
    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============ Distributor Schemas ============

class DistributorBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    legal_name: str = Field(..., min_length=2, max_length=255)
    gstin: str = Field(..., pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
    pan: str = Field(..., pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
    address: str = Field(..., min_length=10)
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    pincode: str = Field(..., pattern=r"^\d{6}$")
    phone: str = Field(..., pattern=r"^\+?[1-9]\d{1,14}$")
    email: EmailStr
    drug_license_number: str = Field(..., min_length=5, max_length=50)
    drug_license_form: Literal["Form 20", "Form 21", "Form 20B", "Form 21B"]
    drug_license_expiry: date
    fssai_license: Optional[str] = None
    credit_limit: Decimal = Field(default=0, ge=0)
    payment_terms_days: int = Field(default=30, ge=0, le=365)
    bank_details: Optional[Dict[str, Any]] = None


class DistributorCreate(DistributorBase):
    pass


class DistributorUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    legal_name: Optional[str] = Field(None, min_length=2, max_length=255)
    address: Optional[str] = Field(None, min_length=10)
    city: Optional[str] = Field(None, min_length=2, max_length=100)
    state: Optional[str] = Field(None, min_length=2, max_length=100)
    pincode: Optional[str] = Field(None, pattern=r"^\d{6}$")
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")
    email: Optional[EmailStr] = None
    drug_license_number: Optional[str] = Field(None, min_length=5, max_length=50)
    drug_license_form: Optional[Literal["Form 20", "Form 21", "Form 20B", "Form 21B"]] = None
    drug_license_expiry: Optional[date] = None
    fssai_license: Optional[str] = None
    credit_limit: Optional[Decimal] = Field(None, ge=0)
    payment_terms_days: Optional[int] = Field(None, ge=0, le=365)
    bank_details: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class DistributorResponse(DistributorBase, IDMixin, TimestampMixin):
    is_active: bool
    
    class Config:
        from_attributes = True


class DistributorListResponse(BaseModel):
    distributors: List[DistributorResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============ Retailer Schemas ============

class RetailerBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    legal_name: str = Field(..., min_length=2, max_length=255)
    gstin: str = Field(..., pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
    pan: str = Field(..., pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
    address: str = Field(..., min_length=10)
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    pincode: str = Field(..., pattern=r"^\d{6}$")
    phone: str = Field(..., pattern=r"^\+?[1-9]\d{1,14}$")
    email: EmailStr
    drug_license_number: str = Field(..., min_length=5, max_length=50)
    drug_license_form: Literal["Form 20", "Form 21", "Form 20B", "Form 21B"]
    drug_license_expiry: date
    fssai_license: Optional[str] = None
    retailer_type: Literal["pharmacy", "chemist", "hospital", "lab"]
    credit_limit: Decimal = Field(default=0, ge=0)
    payment_terms_days: int = Field(default=30, ge=0, le=365)


class RetailerCreate(RetailerBase):
    distributor_id: Optional[UUID] = None


class RetailerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    legal_name: Optional[str] = Field(None, min_length=2, max_length=255)
    address: Optional[str] = Field(None, min_length=10)
    city: Optional[str] = Field(None, min_length=2, max_length=100)
    state: Optional[str] = Field(None, min_length=2, max_length=100)
    pincode: Optional[str] = Field(None, pattern=r"^\d{6}$")
    phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")
    email: Optional[EmailStr] = None
    drug_license_number: Optional[str] = Field(None, min_length=5, max_length=50)
    drug_license_form: Optional[Literal["Form 20", "Form 21", "Form 20B", "Form 21B"]] = None
    drug_license_expiry: Optional[date] = None
    fssai_license: Optional[str] = None
    retailer_type: Optional[Literal["pharmacy", "chemist", "hospital", "lab"]] = None
    credit_limit: Optional[Decimal] = Field(None, ge=0)
    payment_terms_days: Optional[int] = Field(None, ge=0, le=365)
    is_active: Optional[bool] = None


class RetailerVerifyRequest(BaseModel):
    action: Literal["approve", "reject"]
    notes: Optional[str] = None


class RetailerResponse(RetailerBase, IDMixin, TimestampMixin):
    is_verified: bool
    verified_at: Optional[datetime] = None
    verified_by: Optional[UUID] = None
    used_credit: Decimal
    outstanding_balance: Decimal
    overdue_days: int
    is_active: bool
    
    class Config:
        from_attributes = True


class RetailerListResponse(BaseModel):
    retailers: List[RetailerResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============ Warehouse Schemas ============

class WarehouseBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    code: str = Field(..., min_length=2, max_length=20, pattern=r"^[A-Z0-9_-]+$")
    warehouse_type: WarehouseType
    address: str = Field(..., min_length=10)
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    pincode: str = Field(..., pattern=r"^\d{6}$")
    is_default: bool = False


class WarehouseCreate(WarehouseBase):
    pass


class WarehouseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    warehouse_type: Optional[WarehouseType] = None
    address: Optional[str] = Field(None, min_length=10)
    city: Optional[str] = Field(None, min_length=2, max_length=100)
    state: Optional[str] = Field(None, min_length=2, max_length=100)
    pincode: Optional[str] = Field(None, pattern=r"^\d{6}$")
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class WarehouseResponse(WarehouseBase, IDMixin, TimestampMixin):
    distributor_id: UUID
    is_active: bool
    
    class Config:
        from_attributes = True


# ============ Category Schemas ============

class CategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    sort_order: int = 0


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryResponse(CategoryBase, IDMixin, TimestampMixin):
    is_active: bool
    
    class Config:
        from_attributes = True


# ============ Manufacturer Schemas ============

class ManufacturerBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: str = "India"
    gstin: Optional[str] = Field(None, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")
    contact_email: Optional[EmailStr] = None


class ManufacturerCreate(ManufacturerBase):
    pass


class ManufacturerUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    address: Optional[str] = None
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = None
    gstin: Optional[str] = Field(None, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = Field(None, pattern=r"^\+?[1-9]\d{1,14}$")
    contact_email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


class ManufacturerResponse(ManufacturerBase, IDMixin, TimestampMixin):
    is_active: bool
    
    class Config:
        from_attributes = True


# ============ Product Schemas ============

class ProductBase(BaseModel):
    sku: str = Field(..., min_length=2, max_length=50, pattern=r"^[A-Z0-9_-]+$")
    barcode: Optional[str] = Field(None, max_length=50)
    name: str = Field(..., min_length=2, max_length=255)
    generic_name: str = Field(..., min_length=2, max_length=255)
    short_description: Optional[str] = Field(None, max_length=500)
    long_description: Optional[str] = None
    category_id: UUID
    manufacturer_id: UUID
    hsn_code: str = Field(..., pattern=r"^\d{4,8}$")
    drug_license_required: bool = True
    schedule: Optional[str] = Field(None, max_length=20)
    is_prescription_required: bool = False
    strength: Optional[str] = Field(None, max_length=100)
    dosage_form: Optional[str] = Field(None, max_length=50)
    pack_size: str = Field(..., min_length=1, max_length=50)
    unit_of_measure: str = Field(default="unit", max_length=20)
    mrp: Decimal = Field(..., ge=0, decimal_places=2)
    trade_price: Decimal = Field(..., ge=0, decimal_places=2)
    gst_rate: Decimal = Field(default=12.00, ge=0, le=28, decimal_places=2)
    min_order_qty: int = Field(default=1, ge=1)
    max_order_qty: Optional[int] = Field(None, ge=1)
    reorder_level: int = Field(default=10, ge=0)
    is_cold_chain: bool = False
    is_instrument: bool = False
    instrument_specs: Optional[Dict[str, Any]] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    barcode: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    generic_name: Optional[str] = Field(None, min_length=2, max_length=255)
    short_description: Optional[str] = Field(None, max_length=500)
    long_description: Optional[str] = None
    category_id: Optional[UUID] = None
    manufacturer_id: Optional[UUID] = None
    hsn_code: Optional[str] = Field(None, pattern=r"^\d{4,8}$")
    drug_license_required: Optional[bool] = None
    schedule: Optional[str] = Field(None, max_length=20)
    is_prescription_required: Optional[bool] = None
    strength: Optional[str] = Field(None, max_length=100)
    dosage_form: Optional[str] = Field(None, max_length=50)
    pack_size: Optional[str] = Field(None, min_length=1, max_length=50)
    unit_of_measure: Optional[str] = Field(None, max_length=20)
    mrp: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    trade_price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    gst_rate: Optional[Decimal] = Field(None, ge=0, le=28, decimal_places=2)
    min_order_qty: Optional[int] = Field(None, ge=1)
    max_order_qty: Optional[int] = Field(None, ge=1)
    reorder_level: Optional[int] = Field(None, ge=0)
    is_cold_chain: Optional[bool] = None
    is_instrument: Optional[bool] = None
    instrument_specs: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_discontinued: Optional[bool] = None


class ProductSearchFilters(BaseModel):
    query: Optional[str] = None
    category_id: Optional[UUID] = None
    manufacturer_id: Optional[UUID] = None
    dosage_form: Optional[str] = None
    is_instrument: Optional[bool] = None
    is_cold_chain: Optional[bool] = None
    in_stock_only: bool = True
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    expiry_within_days: Optional[int] = Field(None, ge=1, le=365)


class ProductResponse(ProductBase, IDMixin, TimestampMixin):
    distributor_id: UUID
    is_active: bool
    is_discontinued: bool
    discontinued_at: Optional[datetime] = None
    manufacturer: Optional[ManufacturerResponse] = None
    available_stock: int = 0
    
    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    products: List[ProductResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============ Product Batch Schemas ============

class ProductBatchBase(BaseModel):
    product_id: UUID
    batch_number: str = Field(..., min_length=1, max_length=50)
    manufacture_date: date
    expiry_date: date
    mrp: Decimal = Field(..., ge=0, decimal_places=2)
    trade_price: Decimal = Field(..., ge=0, decimal_places=2)
    received_quantity: int = Field(..., ge=0)
    warehouse_id: UUID
    supplier_invoice_number: Optional[str] = None
    supplier_invoice_date: Optional[date] = None
    cost_price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)


class ProductBatchCreate(ProductBatchBase):
    @model_validator(mode="after")
    def validate_dates(self) -> "ProductBatchCreate":
        if self.expiry_date < self.manufacture_date:
            raise ValueError("Expiry date must be after manufacture date")
        return self


class ProductBatchUpdate(BaseModel):
    batch_number: Optional[str] = Field(None, min_length=1, max_length=50)
    manufacture_date: Optional[date] = None
    expiry_date: Optional[date] = None
    mrp: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    trade_price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    received_quantity: Optional[int] = Field(None, ge=0)
    warehouse_id: Optional[UUID] = None
    supplier_invoice_number: Optional[str] = None
    supplier_invoice_date: Optional[date] = None
    cost_price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    is_active: Optional[bool] = None


class ProductBatchResponse(ProductBatchBase, IDMixin, TimestampMixin):
    available_quantity: int
    product: Optional[ProductResponse] = None
    warehouse: Optional[WarehouseResponse] = None
    days_to_expiry: Optional[int] = None
    is_expiring_soon: Optional[bool] = None
    
    class Config:
        from_attributes = True


# ============ Inventory Schemas ============

class InventoryResponse(BaseModel):
    product_id: UUID
    batch_id: UUID
    warehouse_id: UUID
    quantity_on_hand: int
    quantity_reserved: int
    quantity_available: int
    last_stock_take: Optional[datetime] = None
    last_movement: Optional[datetime] = None
    product: Optional[ProductResponse] = None
    batch: Optional[ProductBatchResponse] = None
    warehouse: Optional[WarehouseResponse] = None
    
    class Config:
        from_attributes = True


class StockMovementCreate(BaseModel):
    inventory_id: UUID
    movement_type: Literal["in", "out", "transfer", "adjustment", "return"]
    quantity: int
    reference_type: Optional[str] = None
    reference_id: Optional[UUID] = None
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    notes: Optional[str] = None


class StockMovementResponse(StockMovementCreate, IDMixin, TimestampMixin):
    performed_by: Optional[UUID] = None
    
    class Config:
        from_attributes = True


# ============ Product Substitute Schemas ============

class ProductSubstituteBase(BaseModel):
    product_id: UUID
    substitute_product_id: UUID
    is_generic_equivalent: bool = True
    priority: int = Field(default=1, ge=1)
    notes: Optional[str] = None
    
    @model_validator(mode="after")
    def validate_not_same(self) -> "ProductSubstituteBase":
        if self.product_id == self.substitute_product_id:
            raise ValueError("Product cannot be its own substitute")
        return self


class ProductSubstituteCreate(ProductSubstituteBase):
    pass


class ProductSubstituteResponse(ProductSubstituteBase, IDMixin, TimestampMixin):
    product: Optional[ProductResponse] = None
    substitute_product: Optional[ProductResponse] = None
    
    class Config:
        from_attributes = True


# ============ Pricing Scheme Schemas ============

class PricingSchemeBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None
    scheme_type: SchemeType
    scheme_config: Dict[str, Any]
    applicable_product_ids: Optional[List[UUID]] = None
    applicable_category_ids: Optional[List[UUID]] = None
    applicable_retailer_ids: Optional[List[UUID]] = None
    min_order_value: Optional[Decimal] = Field(None, ge=0)
    max_discount_per_order: Optional[Decimal] = Field(None, ge=0)
    start_date: date
    end_date: Optional[date] = None
    priority: int = 0


class PricingSchemeCreate(PricingSchemeBase):
    pass


class PricingSchemeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = None
    scheme_config: Optional[Dict[str, Any]] = None
    applicable_product_ids: Optional[List[UUID]] = None
    applicable_category_ids: Optional[List[UUID]] = None
    applicable_retailer_ids: Optional[List[UUID]] = None
    min_order_value: Optional[Decimal] = Field(None, ge=0)
    max_discount_per_order: Optional[Decimal] = Field(None, ge=0)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None


class PricingSchemeResponse(PricingSchemeBase, IDMixin, TimestampMixin):
    distributor_id: UUID
    is_active: bool
    
    class Config:
        from_attributes = True


# ============ Order Schemas ============

class OrderItemCreate(BaseModel):
    product_id: UUID
    batch_id: Optional[UUID] = None
    ordered_qty: int = Field(..., ge=1)
    unit_price: Optional[Decimal] = Field(None, ge=0, decimal_places=2)  # If None, calculated from schemes


class OrderCreate(BaseModel):
    retailer_id: UUID
    warehouse_id: Optional[UUID] = None
    items: List[OrderItemCreate] = Field(..., min_length=1)
    expected_delivery_date: Optional[date] = None
    shipping_address: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_pincode: Optional[str] = Field(None, pattern=r"^\d{6}$")
    shipping_contact_name: Optional[str] = None
    shipping_contact_phone: Optional[str] = None
    retailer_notes: Optional[str] = None


class OrderItemUpdate(BaseModel):
    ordered_qty: Optional[int] = Field(None, ge=1)
    batch_id: Optional[UUID] = None


class OrderUpdate(BaseModel):
    warehouse_id: Optional[UUID] = None
    expected_delivery_date: Optional[date] = None
    shipping_address: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_pincode: Optional[str] = Field(None, pattern=r"^\d{6}$")
    shipping_contact_name: Optional[str] = None
    shipping_contact_phone: Optional[str] = None
    retailer_notes: Optional[str] = None
    internal_notes: Optional[str] = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    notes: Optional[str] = None


class OrderCreditCheckRequest(BaseModel):
    approve: bool
    notes: Optional[str] = None


class OrderItemResponse(BaseModel):
    id: UUID
    order_id: UUID
    product_id: UUID
    batch_id: Optional[UUID] = None
    product_name: str
    product_sku: str
    product_generic_name: str
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    hsn_code: str
    gst_rate: Decimal
    unit_of_measure: str
    pack_size: str
    ordered_qty: int
    packed_qty: int
    delivered_qty: int
    returned_qty: int
    unit_price: Decimal
    mrp: Decimal
    discount_per_unit: Decimal
    scheme_applied: Optional[Dict[str, Any]] = None
    line_subtotal: Decimal
    line_discount: Decimal
    line_tax: Decimal
    line_total: Decimal
    is_packed: bool
    is_invoiced: bool
    is_dispatched: bool
    
    class Config:
        from_attributes = True


class OrderResponse(IDMixin, TimestampMixin):
    order_number: str
    status: OrderStatus
    distributor_id: UUID
    retailer_id: UUID
    warehouse_id: Optional[UUID] = None
    created_by: UUID
    approved_by: Optional[UUID] = None
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    credit_checked: bool
    credit_check_passed: bool
    credit_check_notes: Optional[str] = None
    credit_checked_at: Optional[datetime] = None
    credit_checked_by: Optional[UUID] = None
    order_date: date
    expected_delivery_date: Optional[date] = None
    approved_at: Optional[datetime] = None
    invoiced_at: Optional[datetime] = None
    dispatched_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    shipping_address: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_pincode: Optional[str] = None
    shipping_contact_name: Optional[str] = None
    shipping_contact_phone: Optional[str] = None
    retailer_notes: Optional[str] = None
    internal_notes: Optional[str] = None
    cancellation_reason: Optional[str] = None
    items: List[OrderItemResponse] = []
    retailer: Optional[RetailerResponse] = None
    distributor: Optional[DistributorResponse] = None
    warehouse: Optional[WarehouseResponse] = None
    status_history: List["OrderStatusHistoryResponse"] = []
    
    class Config:
        from_attributes = True


class OrderStatusHistoryResponse(IDMixin, TimestampMixin):
    order_id: UUID
    from_status: Optional[OrderStatus] = None
    to_status: OrderStatus
    changed_by: Optional[UUID] = None
    notes: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    orders: List[OrderResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============ Invoice Schemas ============

class InvoiceItemResponse(BaseModel):
    id: UUID
    invoice_id: UUID
    order_item_id: Optional[UUID] = None
    product_name: str
    product_sku: str
    hsn_code: str
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    unit_of_measure: str
    pack_size: str
    quantity: int
    unit_price: Decimal
    discount: Decimal
    taxable_value: Decimal
    gst_rate: Decimal
    cgst_rate: Decimal
    sgst_rate: Decimal
    igst_rate: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_amount: Decimal
    
    class Config:
        from_attributes = True


class InvoiceResponse(IDMixin, TimestampMixin):
    invoice_number: str
    invoice_series: str
    status: InvoiceStatus
    distributor_id: UUID
    retailer_id: UUID
    order_id: UUID
    taxable_value: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_tax: Decimal
    total_amount: Decimal
    round_off: Decimal
    place_of_supply: str
    supply_type: str
    reverse_charge: bool
    irn: Optional[str] = None
    ack_no: Optional[str] = None
    ack_date: Optional[datetime] = None
    qr_code: Optional[str] = None
    e_invoice_errors: Optional[Dict[str, Any]] = None
    invoice_date: date
    due_date: date
    generated_at: Optional[datetime] = None
    payment_status: PaymentStatus
    paid_amount: Decimal
    balance_amount: Decimal
    items: List[InvoiceItemResponse] = []
    order: Optional[OrderResponse] = None
    retailer: Optional[RetailerResponse] = None
    distributor: Optional[DistributorResponse] = None
    
    class Config:
        from_attributes = True


class InvoiceGenerateRequest(BaseModel):
    order_id: UUID
    invoice_series: Literal["B2B", "B2C", "EXP"] = "B2B"
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None


class InvoiceListResponse(BaseModel):
    invoices: List[InvoiceResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============ Payment Schemas ============

class PaymentCreate(BaseModel):
    invoice_id: UUID
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    payment_mode: Literal["cash", "cheque", "neft", "rtgs", "upi", "bank_transfer"]
    reference_number: Optional[str] = None
    payment_date: date
    notes: Optional[str] = None
    bank_name: Optional[str] = None
    cheque_date: Optional[date] = None


class PaymentResponse(PaymentCreate, IDMixin, TimestampMixin):
    clearance_date: Optional[date] = None
    is_reconciled: bool
    received_by: Optional[UUID] = None
    
    class Config:
        from_attributes = True


class PaymentListResponse(BaseModel):
    payments: List[PaymentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============ Credit Note Schemas ============

class CreditNoteItemResponse(BaseModel):
    id: UUID
    credit_note_id: UUID
    invoice_item_id: Optional[UUID] = None
    product_name: str
    hsn_code: str
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    quantity: int
    unit_price: Decimal
    taxable_value: Decimal
    gst_rate: Decimal
    total_amount: Decimal
    
    class Config:
        from_attributes = True


class CreditNoteResponse(IDMixin, TimestampMixin):
    credit_note_number: str
    invoice_id: UUID
    return_request_id: Optional[UUID] = None
    reason: str
    taxable_value: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_amount: Decimal
    place_of_supply: str
    supply_type: str
    status: str
    irn: Optional[str] = None
    issued_at: Optional[datetime] = None
    issued_by: Optional[UUID] = None
    items: List[CreditNoteItemResponse] = []
    invoice: Optional[InvoiceResponse] = None
    
    class Config:
        from_attributes = True


# ============ Return Request Schemas ============

class ReturnRequestItemCreate(BaseModel):
    invoice_item_id: UUID
    quantity: int = Field(..., ge=1)
    reason: Optional[str] = None


class ReturnRequestCreate(BaseModel):
    invoice_id: UUID
    reason: ReturnReason
    reason_description: Optional[str] = None
    items: List[ReturnRequestItemCreate] = Field(..., min_length=1)


class ReturnRequestItemUpdate(BaseModel):
    approved_quantity: int = Field(..., ge=0)
    rejected_quantity: int = Field(..., ge=0)
    rejection_reason: Optional[str] = None


class ReturnRequestProcessRequest(BaseModel):
    action: Literal["approve", "reject"]
    items: List[ReturnRequestItemUpdate]
    processor_notes: Optional[str] = None


class ReturnRequestInspectionRequest(BaseModel):
    passed: bool
    notes: Optional[str] = None


class ReturnRequestItemResponse(BaseModel):
    id: UUID
    return_request_id: UUID
    invoice_item_id: UUID
    order_item_id: Optional[UUID] = None
    product_name: str
    batch_number: Optional[str] = None
    expiry_date: Optional[date] = None
    quantity: int
    unit_price: Decimal
    total_amount: Decimal
    approved_quantity: int
    rejected_quantity: int
    rejection_reason: Optional[str] = None
    
    class Config:
        from_attributes = True


class ReturnRequestResponse(IDMixin, TimestampMixin):
    return_number: str
    retailer_id: UUID
    invoice_id: UUID
    order_id: Optional[UUID] = None
    reason: ReturnReason
    reason_description: Optional[str] = None
    status: str
    requested_by: UUID
    processed_by: Optional[UUID] = None
    processed_at: Optional[datetime] = None
    processor_notes: Optional[str] = None
    requires_inspection: bool
    inspection_passed: Optional[bool] = None
    inspection_notes: Optional[str] = None
    inspected_by: Optional[UUID] = None
    inspected_at: Optional[datetime] = None
    requested_at: datetime
    approved_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    items: List[ReturnRequestItemResponse] = []
    retailer: Optional[RetailerResponse] = None
    credit_note: Optional[CreditNoteResponse] = None
    
    class Config:
        from_attributes = True


class ReturnRequestListResponse(BaseModel):
    returns: List[ReturnRequestResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============ E-Way Bill Schemas ============

class EWayBillCreate(BaseModel):
    order_id: Optional[UUID] = None
    invoice_id: Optional[UUID] = None
    gstin_supplier: str = Field(..., pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
    gstin_recipient: str = Field(..., pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
    place_of_dispatch: str
    place_of_delivery: str
    document_type: Literal["INV", "CN", "DN"]
    document_number: str
    document_date: date
    transaction_type: Literal["Regular", "Bill To Ship To"]
    value_of_goods: Decimal = Field(..., gt=0)
    hsn_codes: List[str] = Field(..., min_length=1)
    reason_for_transportation: str
    transporter_id: Optional[str] = None
    transporter_name: Optional[str] = None
    vehicle_number: Optional[str] = None
    transport_mode: Optional[Literal["Road", "Rail", "Air", "Ship"]] = None
    transport_doc_number: Optional[str] = None
    transport_doc_date: Optional[date] = None
    distance: Optional[int] = Field(None, ge=1)


class EWayBillResponse(EWayBillCreate, IDMixin, TimestampMixin):
    eway_bill_number: Optional[str] = None
    eway_bill_date: Optional[datetime] = None
    valid_upto: Optional[datetime] = None
    status: str
    error_message: Optional[str] = None
    generated_by: Optional[UUID] = None
    cancelled_at: Optional[datetime] = None
    cancelled_by: Optional[UUID] = None
    cancellation_reason: Optional[str] = None
    
    class Config:
        from_attributes = True


# ============ Ledger Schemas ============

class LedgerEntryResponse(BaseModel):
    id: UUID
    retailer_id: UUID
    invoice_id: Optional[UUID] = None
    payment_id: Optional[UUID] = None
    credit_note_id: Optional[UUID] = None
    entry_type: str
    description: str
    debit_amount: Decimal
    credit_amount: Decimal
    balance: Decimal
    entry_date: date
    reference_number: Optional[str] = None
    
    class Config:
        from_attributes = True


class LedgerSummaryResponse(BaseModel):
    retailer_id: UUID
    retailer_name: str
    opening_balance: Decimal
    total_invoices: Decimal
    total_payments: Decimal
    total_credit_notes: Decimal
    closing_balance: Decimal
    credit_limit: Decimal
    available_credit: Decimal
    overdue_amount: Decimal
    overdue_days: int
    entries: List[LedgerEntryResponse] = []


# ============ Picking Slip Schemas ============

class PickingSlipItemResponse(BaseModel):
    product_id: UUID
    product_name: str
    product_sku: str
    batch_id: UUID
    batch_number: str
    expiry_date: date
    quantity: int
    warehouse_location: Optional[str] = None
    is_instrument: bool
    instrument_check_required: bool
    instrument_check_passed: Optional[bool] = None
    
    class Config:
        from_attributes = True


class PickingSlipResponse(BaseModel):
    id: UUID
    order_id: UUID
    warehouse_id: UUID
    slip_number: str
    status: str
    items: List[PickingSlipItemResponse] = []
    created_by: UUID
    packed_by: Optional[UUID] = None
    packed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# ============ Dashboard/Analytics Schemas ============

class DistributorDashboardStats(BaseModel):
    total_retailers: int
    active_retailers: int
    pending_verification: int
    total_orders_today: int
    total_orders_this_month: int
    revenue_today: Decimal
    revenue_this_month: Decimal
    outstanding_receivables: Decimal
    overdue_receivables: Decimal
    low_stock_products: int
    expiring_soon_products: int
    pending_returns: int


class RetailerDashboardStats(BaseModel):
    my_orders_count: int
    pending_orders: int
    delivered_orders: int
    outstanding_balance: Decimal
    credit_limit: Decimal
    available_credit: Decimal
    overdue_amount: Decimal
    overdue_days: int
    recent_invoices: List[InvoiceResponse] = []
    recent_orders: List[OrderResponse] = []


# ============ Pagination ============

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: Optional[str] = None
    sort_order: Literal["asc", "desc"] = "desc"


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int