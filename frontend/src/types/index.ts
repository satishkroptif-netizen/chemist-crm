export interface User {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  role: UserRole;
  status: UserStatus;
  is_active: boolean;
  distributor_id: string | null;
  retailer_id: string | null;
  last_login: string | null;
  avatar_url: string | null;
  created_at: string;
  updated_at: string;
}

export type UserRole = 
  | 'super_admin' 
  | 'distributor_admin' 
  | 'distributor_staff' 
  | 'retailer_admin' 
  | 'retailer_staff';

export type UserStatus = 
  | 'pending_verification' 
  | 'active' 
  | 'suspended' 
  | 'rejected';

export interface Distributor {
  id: string;
  name: string;
  legal_name: string;
  gstin: string;
  pan: string;
  address: string;
  city: string;
  state: string;
  pincode: string;
  phone: string;
  email: string;
  drug_license_number: string;
  drug_license_form: string;
  drug_license_expiry: string;
  fssai_license: string | null;
  is_active: boolean;
  credit_limit: number;
  payment_terms_days: number;
  bank_details: Record<string, any> | null;
  created_at: string;
  updated_at: string;
}

export interface Retailer {
  id: string;
  name: string;
  legal_name: string;
  gstin: string;
  pan: string;
  address: string;
  city: string;
  state: string;
  pincode: string;
  phone: string;
  email: string;
  drug_license_number: string;
  drug_license_form: string;
  drug_license_expiry: string;
  fssai_license: string | null;
  retailer_type: 'pharmacy' | 'chemist' | 'hospital' | 'lab';
  is_verified: boolean;
  verified_at: string | null;
  verified_by: string | null;
  credit_limit: number;
  used_credit: number;
  payment_terms_days: number;
  outstanding_balance: number;
  overdue_days: number;
  is_active: boolean;
  distributor_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Warehouse {
  id: string;
  name: string;
  code: string;
  warehouse_type: 'main' | 'cold_storage' | 'instruments' | 'return';
  address: string;
  city: string;
  state: string;
  pincode: string;
  is_default: boolean;
  is_active: boolean;
  distributor_id: string;
  created_at: string;
  updated_at: string;
}

export interface ProductCategory {
  id: string;
  name: string;
  description: string | null;
  parent_id: string | null;
  is_active: boolean;
  sort_order: number;
  children: ProductCategory[];
  created_at: string;
  updated_at: string;
}

export interface Manufacturer {
  id: string;
  name: string;
  code: string;
  address: string | null;
  city: string | null;
  state: string | null;
  country: string;
  gstin: string | null;
  contact_person: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Product {
  id: string;
  sku: string;
  barcode: string | null;
  name: string;
  generic_name: string;
  short_description: string | null;
  long_description: string | null;
  category_id: string;
  manufacturer_id: string;
  distributor_id: string;
  hsn_code: string;
  drug_license_required: boolean;
  schedule: string | null;
  is_prescription_required: boolean;
  strength: string | null;
  dosage_form: string | null;
  pack_size: string;
  unit_of_measure: string;
  mrp: number;
  trade_price: number;
  gst_rate: number;
  min_order_qty: number;
  max_order_qty: number | null;
  reorder_level: number;
  is_cold_chain: boolean;
  is_instrument: boolean;
  instrument_specs: Record<string, any> | null;
  is_active: boolean;
  is_discontinued: boolean;
  discontinued_at: string | null;
  manufacturer?: Manufacturer;
  category?: ProductCategory;
  available_stock: number;
  batches?: ProductBatch[];
  created_at: string;
  updated_at: string;
}

export interface ProductBatch {
  id: string;
  product_id: string;
  batch_number: string;
  manufacture_date: string;
  expiry_date: string;
  mrp: number;
  trade_price: number;
  received_quantity: number;
  available_quantity: number;
  warehouse_id: string;
  supplier_invoice_number: string | null;
  supplier_invoice_date: string | null;
  cost_price: number | null;
  is_active: boolean;
  product?: Product;
  warehouse?: Warehouse;
  days_to_expiry: number;
  is_expiring_soon: boolean;
  created_at: string;
  updated_at: string;
}

export interface Inventory {
  product_id: string;
  batch_id: string;
  warehouse_id: string;
  quantity_on_hand: number;
  quantity_reserved: number;
  quantity_available: number;
  last_stock_take: string | null;
  last_movement: string | null;
  product?: Product;
  batch?: ProductBatch;
  warehouse?: Warehouse;
}

export interface PricingScheme {
  id: string;
  distributor_id: string;
  name: string;
  description: string | null;
  scheme_type: 'buy_get_free' | 'volume_discount' | 'net_rate' | 'flat_discount';
  scheme_config: Record<string, any>;
  applicable_product_ids: string[] | null;
  applicable_category_ids: string[] | null;
  applicable_retailer_ids: string[] | null;
  min_order_value: number | null;
  max_discount_per_order: number | null;
  start_date: string;
  end_date: string | null;
  is_active: boolean;
  priority: number;
  created_at: string;
  updated_at: string;
}

export type OrderStatus = 
  | 'draft' 
  | 'submitted' 
  | 'approved_by_credit' 
  | 'picking' 
  | 'invoiced' 
  | 'dispatched' 
  | 'delivered' 
  | 'closed' 
  | 'cancelled' 
  | 'return_requested' 
  | 'return_approved' 
  | 'return_rejected' 
  | 'credit_note_issued';

export interface OrderItem {
  id: string;
  order_id: string;
  product_id: string;
  batch_id: string | null;
  product_name: string;
  product_sku: string;
  product_generic_name: string;
  batch_number: string | null;
  expiry_date: string | null;
  hsn_code: string;
  gst_rate: number;
  unit_of_measure: string;
  pack_size: string;
  ordered_qty: number;
  packed_qty: number;
  delivered_qty: number;
  returned_qty: number;
  unit_price: number;
  mrp: number;
  discount_per_unit: number;
  scheme_applied: Record<string, any> | null;
  line_subtotal: number;
  line_discount: number;
  line_tax: number;
  line_total: number;
  is_packed: boolean;
  is_invoiced: boolean;
  is_dispatched: boolean;
  product?: Product;
  batch?: ProductBatch;
}

export interface OrderStatusHistory {
  id: string;
  order_id: string;
  from_status: OrderStatus | null;
  to_status: OrderStatus;
  changed_by: string | null;
  notes: string | null;
  metadata: Record<string, any> | null;
  created_at: string;
}

export interface Order {
  id: string;
  order_number: string;
  status: OrderStatus;
  distributor_id: string;
  retailer_id: string;
  warehouse_id: string | null;
  created_by: string;
  approved_by: string | null;
  subtotal: number;
  discount_amount: number;
  tax_amount: number;
  total_amount: number;
  credit_checked: boolean;
  credit_check_passed: boolean;
  credit_check_notes: string | null;
  credit_checked_at: string | null;
  credit_checked_by: string | null;
  order_date: string;
  expected_delivery_date: string | null;
  approved_at: string | null;
  invoiced_at: string | null;
  dispatched_at: string | null;
  delivered_at: string | null;
  closed_at: string | null;
  shipping_address: string | null;
  shipping_city: string | null;
  shipping_state: string | null;
  shipping_pincode: string | null;
  shipping_contact_name: string | null;
  shipping_contact_phone: string | null;
  retailer_notes: string | null;
  internal_notes: string | null;
  cancellation_reason: string | null;
  items: OrderItem[];
  retailer?: Retailer;
  distributor?: Distributor;
  warehouse?: Warehouse;
  status_history: OrderStatusHistory[];
  created_at: string;
  updated_at: string;
}

export type InvoiceStatus = 'draft' | 'generated' | 'e_invoice_pending' | 'e_invoice_generated' | 'cancelled';
export type PaymentStatus = 'pending' | 'partial' | 'paid' | 'overdue' | 'write_off';

export interface InvoiceItem {
  id: string;
  invoice_id: string;
  order_item_id: string | null;
  product_name: string;
  product_sku: string;
  hsn_code: string;
  batch_number: string | null;
  expiry_date: string | null;
  unit_of_measure: string;
  pack_size: string;
  quantity: number;
  unit_price: number;
  discount: number;
  taxable_value: number;
  gst_rate: number;
  cgst_rate: number;
  sgst_rate: number;
  igst_rate: number;
  cgst_amount: number;
  sgst_amount: number;
  igst_amount: number;
  total_amount: number;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  invoice_series: string;
  status: InvoiceStatus;
  distributor_id: string;
  retailer_id: string;
  order_id: string;
  taxable_value: number;
  cgst_amount: number;
  sgst_amount: number;
  igst_amount: number;
  total_tax: number;
  total_amount: number;
  round_off: number;
  place_of_supply: string;
  supply_type: string;
  reverse_charge: boolean;
  irn: string | null;
  ack_no: string | null;
  ack_date: string | null;
  qr_code: string | null;
  e_invoice_errors: Record<string, any> | null;
  invoice_date: string;
  due_date: string;
  generated_at: string | null;
  payment_status: PaymentStatus;
  paid_amount: number;
  balance_amount: number;
  items: InvoiceItem[];
  order?: Order;
  retailer?: Retailer;
  distributor?: Distributor;
  created_at: string;
  updated_at: string;
}

export interface Payment {
  id: string;
  invoice_id: string;
  payment_number: string;
  amount: number;
  payment_mode: 'cash' | 'cheque' | 'neft' | 'rtgs' | 'upi' | 'bank_transfer';
  reference_number: string | null;
  payment_date: string;
  received_by: string | null;
  notes: string | null;
  bank_name: string | null;
  cheque_date: string | null;
  clearance_date: string | null;
  is_reconciled: boolean;
  created_at: string;
  updated_at: string;
}

export type ReturnReason = 'breakage' | 'spoilage' | 'expired' | 'wrong_item' | 'quality_issue' | 'excess_stock';

export interface ReturnRequestItem {
  id: string;
  return_request_id: string;
  invoice_item_id: string;
  order_item_id: string | null;
  product_name: string;
  batch_number: string | null;
  expiry_date: string | null;
  quantity: number;
  unit_price: number;
  total_amount: number;
  approved_quantity: number;
  rejected_quantity: number;
  rejection_reason: string | null;
}

export interface ReturnRequest {
  id: string;
  return_number: string;
  retailer_id: string;
  invoice_id: string;
  order_id: string | null;
  reason: ReturnReason;
  reason_description: string | null;
  status: string;
  requested_by: string;
  processed_by: string | null;
  processed_at: string | null;
  processor_notes: string | null;
  requires_inspection: boolean;
  inspection_passed: boolean | null;
  inspection_notes: string | null;
  inspected_by: string | null;
  inspected_at: string | null;
  requested_at: string;
  approved_at: string | null;
  received_at: string | null;
  items: ReturnRequestItem[];
  retailer?: Retailer;
  credit_note?: CreditNote;
  created_at: string;
  updated_at: string;
}

export interface CreditNote {
  id: string;
  credit_note_number: string;
  invoice_id: string;
  return_request_id: string | null;
  reason: string;
  taxable_value: number;
  cgst_amount: number;
  sgst_amount: number;
  igst_amount: number;
  total_amount: number;
  place_of_supply: string;
  supply_type: string;
  status: string;
  irn: string | null;
  issued_at: string | null;
  issued_by: string | null;
  items: CreditNoteItem[];
  invoice?: Invoice;
}

export interface CreditNoteItem {
  id: string;
  credit_note_id: string;
  invoice_item_id: string | null;
  product_name: string;
  hsn_code: string;
  batch_number: string | null;
  expiry_date: string | null;
  quantity: number;
  unit_price: number;
  taxable_value: number;
  gst_rate: number;
  total_amount: number;
}

export interface EWayBill {
  id: string;
  order_id: string | null;
  invoice_id: string | null;
  eway_bill_number: string | null;
  eway_bill_date: string | null;
  valid_upto: string | null;
  gstin_supplier: string;
  gstin_recipient: string;
  place_of_dispatch: string;
  place_of_delivery: string;
  document_type: string;
  document_number: string;
  document_date: string;
  transaction_type: string;
  value_of_goods: number;
  hsn_codes: string[];
  reason_for_transportation: string;
  transporter_id: string | null;
  transporter_name: string | null;
  vehicle_number: string | null;
  transport_mode: string | null;
  transport_doc_number: string | null;
  transport_doc_date: string | null;
  distance: number | null;
  status: string;
  error_message: string | null;
  generated_by: string | null;
  cancelled_at: string | null;
  cancelled_by: string | null;
  cancellation_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface LedgerEntry {
  id: string;
  retailer_id: string;
  invoice_id: string | null;
  payment_id: string | null;
  credit_note_id: string | null;
  entry_type: string;
  description: string;
  debit_amount: number;
  credit_amount: number;
  balance: number;
  entry_date: string;
  reference_number: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ApiError {
  code: string;
  message: string;
  details: Record<string, any>;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface Token {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}