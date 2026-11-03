import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number | string): string {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount;
  if (isNaN(num)) return '₹0.00';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
}

export function formatNumber(num: number | string): string {
  const n = typeof num === 'string' ? parseFloat(num) : num;
  if (isNaN(n)) return '0';
  return new Intl.NumberFormat('en-IN').format(n);
}

export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return '-';
  try {
    return new Date(dateString).toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return '-';
  }
}

export function formatDateTime(dateString: string | null | undefined): string {
  if (!dateString) return '-';
  try {
    return new Date(dateString).toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '-';
  }
}

export function getDaysUntilExpiry(expiryDate: string): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const expiry = new Date(expiryDate);
  expiry.setHours(0, 0, 0, 0);
  const diffTime = expiry.getTime() - today.getTime();
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
}

export function getExpiryStatus(expiryDate: string): { label: string; className: string } {
  const days = getDaysUntilExpiry(expiryDate);
  if (days < 0) return { label: 'Expired', className: 'badge-danger' };
  if (days <= 30) return { label: `${days} days left`, className: 'badge-danger' };
  if (days <= 90) return { label: `${days} days left`, className: 'badge-warning' };
  return { label: `${days} days left`, className: 'badge-success' };
}

export function getOrderStatusBadge(status: string): { label: string; className: string } {
  const statusMap: Record<string, { label: string; className: string }> = {
    draft: { label: 'Draft', className: 'badge-gray' },
    submitted: { label: 'Submitted', className: 'badge-info' },
    approved_by_credit: { label: 'Approved', className: 'badge-success' },
    picking: { label: 'Picking', className: 'badge-warning' },
    invoiced: { label: 'Invoiced', className: 'badge-info' },
    dispatched: { label: 'Dispatched', className: 'badge-info' },
    delivered: { label: 'Delivered', className: 'badge-success' },
    closed: { label: 'Closed', className: 'badge-gray' },
    cancelled: { label: 'Cancelled', className: 'badge-danger' },
    return_requested: { label: 'Return Requested', className: 'badge-warning' },
    return_approved: { label: 'Return Approved', className: 'badge-success' },
    return_rejected: { label: 'Return Rejected', className: 'badge-danger' },
    credit_note_issued: { label: 'Credit Note Issued', className: 'badge-info' },
  };
  return statusMap[status] || { label: status, className: 'badge-gray' };
}

export function getInvoiceStatusBadge(status: string): { label: string; className: string } {
  const statusMap: Record<string, { label: string; className: string }> = {
    draft: { label: 'Draft', className: 'badge-gray' },
    generated: { label: 'Generated', className: 'badge-success' },
    e_invoice_pending: { label: 'E-Invoice Pending', className: 'badge-warning' },
    e_invoice_generated: { label: 'E-Invoice Generated', className: 'badge-success' },
    cancelled: { label: 'Cancelled', className: 'badge-danger' },
  };
  return statusMap[status] || { label: status, className: 'badge-gray' };
}

export function getPaymentStatusBadge(status: string): { label: string; className: string } {
  const statusMap: Record<string, { label: string; className: string }> = {
    pending: { label: 'Pending', className: 'badge-warning' },
    partial: { label: 'Partial', className: 'badge-info' },
    paid: { label: 'Paid', className: 'badge-success' },
    overdue: { label: 'Overdue', className: 'badge-danger' },
    write_off: { label: 'Written Off', className: 'badge-gray' },
  };
  return statusMap[status] || { label: status, className: 'badge-gray' };
}

export function getReturnReasonLabel(reason: string): string {
  const reasonMap: Record<string, string> = {
    breakage: 'Breakage',
    spoilage: 'Spoilage',
    expired: 'Expired',
    wrong_item: 'Wrong Item',
    quality_issue: 'Quality Issue',
    excess_stock: 'Excess Stock',
  };
  return reasonMap[reason] || reason;
}

export function getReturnStatusBadge(status: string): { label: string; className: string } {
  const statusMap: Record<string, { label: string; className: string }> = {
    pending: { label: 'Pending', className: 'badge-warning' },
    approved: { label: 'Approved', className: 'badge-success' },
    approved_pending_inspection: { label: 'Pending Inspection', className: 'badge-warning' },
    rejected: { label: 'Rejected', className: 'badge-danger' },
    received: { label: 'Received', className: 'badge-info' },
    credit_note_issued: { label: 'Credit Note Issued', className: 'badge-success' },
  };
  return statusMap[status] || { label: status, className: 'badge-gray' };
}

export function generateOrderNumber(prefix: string = 'ORD'): string {
  const today = new Date();
  const dateStr = today.toISOString().slice(0, 10).replace(/-/g, '');
  const random = Math.floor(Math.random() * 10000).toString().padStart(4, '0');
  return `${prefix}${dateStr}${random}`;
}

export function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null;
  return (...args: Parameters<T>) => {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}

export function getInitials(name: string): string {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return str.slice(0, length) + '...';
}