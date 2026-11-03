import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { Token, ApiError } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

class ApiService {
  private client: AxiosInstance;
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private isRefreshing = false;
  private failedQueue: Array<{
    resolve: (token: string) => void;
    reject: (error: Error) => void;
  }> = [];

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 30000,
    });

    this.client.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        if (this.accessToken) {
          config.headers.Authorization = `Bearer ${this.accessToken}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

        if (error.response?.status === 401 && !originalRequest._retry) {
          if (this.isRefreshing) {
            return new Promise((resolve, reject) => {
              this.failedQueue.push({ resolve, reject });
            })
              .then((token) => {
                originalRequest.headers.Authorization = `Bearer ${token}`;
                return this.client(originalRequest);
              })
              .catch((err) => Promise.reject(err));
          }

          originalRequest._retry = true;
          this.isRefreshing = true;

          try {
            const newToken = await this.refreshAccessToken();
            this.failedQueue.forEach(({ resolve }) => resolve(newToken));
            this.failedQueue = [];
            
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            return this.client(originalRequest);
          } catch (refreshError) {
            this.failedQueue.forEach(({ reject }) => reject(refreshError));
            this.failedQueue = [];
            this.clearTokens();
            window.location.href = '/login';
            return Promise.reject(refreshError);
          } finally {
            this.isRefreshing = false;
          }
        }

        return Promise.reject(this.handleError(error));
      }
    );

    // Load tokens from localStorage
    this.loadTokens();
  }

  private loadTokens() {
    this.accessToken = localStorage.getItem('access_token');
    this.refreshToken = localStorage.getItem('refresh_token');
  }

  private saveTokens(token: Token) {
    this.accessToken = token.access_token;
    this.refreshToken = token.refresh_token;
    localStorage.setItem('access_token', token.access_token);
    localStorage.setItem('refresh_token', token.refresh_token);
  }

  private clearTokens() {
    this.accessToken = null;
    this.refreshToken = null;
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }

  private handleError(error: AxiosError): Error {
    if (error.response?.data) {
      const apiError = error.response.data as { error: ApiError };
      return new Error(apiError.error?.message || 'An error occurred');
    }
    if (error.message === 'Network Error') {
      return new Error('Unable to connect to server. Please check your connection.');
    }
    return new Error(error.message || 'An unexpected error occurred');
  }

  async refreshAccessToken(): Promise<string> {
    if (!this.refreshToken) {
      throw new Error('No refresh token available');
    }

    const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
      refresh_token: this.refreshToken,
    });

    const token = response.data as Token;
    this.saveTokens(token);
    return token.access_token;
  }

  setTokens(token: Token) {
    this.saveTokens(token);
  }

  clearAuth() {
    this.clearTokens();
  }

  getAccessToken(): string | null {
    return this.accessToken;
  }

  isAuthenticated(): boolean {
    return !!this.accessToken;
  }

  // Auth endpoints
  async login(email: string, password: string): Promise<Token> {
    const response = await this.client.post<Token>('/auth/login', { email, password });
    this.saveTokens(response.data);
    return response.data;
  }

  async logout(): Promise<void> {
    this.clearAuth();
  }

  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await this.client.post('/auth/change-password', { current_password: currentPassword, new_password: newPassword });
  }

  async getMe() {
    const response = await this.client.get('/users/me');
    return response.data;
  }

  async updateMe(data: Partial<{ full_name: string; phone: string; avatar_url: string }>) {
    const response = await this.client.patch('/users/me', data);
    return response.data;
  }

  // Generic CRUD methods
  async get<T>(url: string, params?: Record<string, any>) {
    const response = await this.client.get<T>(url, { params });
    return response.data;
  }

  async post<T>(url: string, data?: any) {
    const response = await this.client.post<T>(url, data);
    return response.data;
  }

  async patch<T>(url: string, data?: any) {
    const response = await this.client.patch<T>(url, data);
    return response.data;
  }

  async delete(url: string) {
    const response = await this.client.delete(url);
    return response.data;
  }

  // Distributor endpoints
  async getDistributors(params?: { page?: number; page_size?: number; search?: string; is_active?: boolean }) {
    return this.get('/distributors', params);
  }

  async getDistributor(id: string) {
    return this.get<{ distributor: any }>(`/distributors/${id}`);
  }

  async createDistributor(data: any) {
    return this.post('/distributors', data);
  }

  async updateDistributor(id: string, data: any) {
    return this.patch(`/distributors/${id}`, data);
  }

  // Retailer endpoints
  async getRetailers(params?: { page?: number; page_size?: number; search?: string; is_verified?: boolean; is_active?: boolean }) {
    return this.get('/retailers', params);
  }

  async getRetailer(id: string) {
    return this.get<{ retailer: any }>(`/retailers/${id}`);
  }

  async createRetailer(data: any) {
    return this.post('/retailers', data);
  }

  async updateRetailer(id: string, data: any) {
    return this.patch(`/retailers/${id}`, data);
  }

  async verifyRetailer(id: string, action: 'approve' | 'reject', notes?: string) {
    return this.post(`/retailers/${id}/verify`, { action, notes });
  }

  // Warehouse endpoints
  async getWarehouses(params?: { is_active?: boolean; warehouse_type?: string }) {
    return this.get('/warehouses', params);
  }

  async createWarehouse(data: any) {
    return this.post('/warehouses', data);
  }

  async updateWarehouse(id: string, data: any) {
    return this.patch(`/warehouses/${id}`, data);
  }

  // Category endpoints
  async getCategories(params?: { parent_id?: string; is_active?: boolean }) {
    return this.get('/categories', params);
  }

  async createCategory(data: any) {
    return this.post('/categories', data);
  }

  async updateCategory(id: string, data: any) {
    return this.patch(`/categories/${id}`, data);
  }

  // Manufacturer endpoints
  async getManufacturers(params?: { is_active?: boolean; search?: string }) {
    return this.get('/manufacturers', params);
  }

  async createManufacturer(data: any) {
    return this.post('/manufacturers', data);
  }

  async updateManufacturer(id: string, data: any) {
    return this.patch(`/manufacturers/${id}`, data);
  }

  // Product endpoints
  async getProducts(params?: { 
    page?: number; 
    page_size?: number; 
    query?: string; 
    category_id?: string; 
    manufacturer_id?: string;
    in_stock_only?: boolean;
  }) {
    return this.get('/products', params);
  }

  async searchProducts(q: string, params?: { page?: number; page_size?: number }) {
    return this.get('/products/search', { q, ...params });
  }

  async getProduct(id: string) {
    return this.get<{ product: any }>(`/products/${id}`);
  }

  async createProduct(data: any) {
    return this.post('/products', data);
  }

  async updateProduct(id: string, data: any) {
    return this.patch(`/products/${id}`, data);
  }

  async getProductSubstitutes(productId: string) {
    return this.get(`/products/${productId}/substitutes`);
  }

  async addProductSubstitute(productId: string, data: any) {
    return this.post(`/products/${productId}/substitutes`, data);
  }

  // Batch endpoints
  async getBatches(params?: { product_id?: string; warehouse_id?: string; expiring_soon?: boolean }) {
    return this.get('/batches', params);
  }

  async createBatch(data: any) {
    return this.post('/batches', data);
  }

  async updateBatch(id: string, data: any) {
    return this.patch(`/batches/${id}`, data);
  }

  // Inventory endpoints
  async getInventory(params?: { warehouse_id?: string; product_id?: string; low_stock_only?: boolean; expiring_soon?: boolean }) {
    return this.get('/inventory', params);
  }

  async getInventorySummary() {
    return this.get('/inventory/summary');
  }

  async reserveStock(data: { product_id: string; batch_id: string; warehouse_id: string; quantity: number }) {
    return this.post('/inventory/reserve', data);
  }

  async releaseStock(data: { product_id: string; batch_id: string; warehouse_id: string; quantity: number }) {
    return this.post('/inventory/release', data);
  }

  // Pricing Scheme endpoints
  async getPricingSchemes(params?: { is_active?: boolean; scheme_type?: string }) {
    return this.get('/pricing-schemes', params);
  }

  async getApplicableSchemes(data: { retailer_id: string; product_ids: string[]; order_value: number }) {
    return this.post('/pricing-schemes/applicable', data);
  }

  async createPricingScheme(data: any) {
    return this.post('/pricing-schemes', data);
  }

  async updatePricingScheme(id: string, data: any) {
    return this.patch(`/pricing-schemes/${id}`, data);
  }

  // Order endpoints
  async getOrders(params?: { 
    page?: number; 
    page_size?: number; 
    status?: string; 
    retailer_id?: string;
    date_from?: string;
    date_to?: string;
  }) {
    return this.get('/orders', params);
  }

  async getOrder(id: string) {
    return this.get<{ order: any }>(`/orders/${id}`);
  }

  async createOrder(data: any) {
    return this.post('/orders', data);
  }

  async updateOrder(id: string, data: any) {
    return this.patch(`/orders/${id}`, data);
  }

  async submitOrder(id: string) {
    return this.post(`/orders/${id}/submit`);
  }

  async creditCheckOrder(id: string, approve: boolean, notes?: string) {
    return this.post(`/orders/${id}/credit-check`, { approve, notes });
  }

  async updateOrderStatus(id: string, status: string, notes?: string) {
    return this.post(`/orders/${id}/status`, { status, notes });
  }

  async cancelOrder(id: string, reason: string) {
    return this.post(`/orders/${id}/cancel`, { reason });
  }

  async getOrderSubstitutes(id: string) {
    return this.get(`/orders/${id}/substitutes`);
  }

  // Invoice endpoints
  async getInvoices(params?: { 
    page?: number; 
    page_size?: number; 
    status?: string; 
    retailer_id?: string;
    payment_status?: string;
    date_from?: string;
    date_to?: string;
  }) {
    return this.get('/invoices', params);
  }

  async getInvoice(id: string) {
    return this.get<{ invoice: any }>(`/invoices/${id}`);
  }

  async generateInvoice(data: { order_id: string; invoice_series?: string; invoice_date?: string; due_date?: string }) {
    return this.post('/invoices/generate', data);
  }

  async cancelInvoice(id: string, reason: string) {
    return this.post(`/invoices/${id}/cancel`, { reason });
  }

  async downloadInvoice(id: string) {
    return this.get(`/invoices/${id}/download`);
  }

  // Payment endpoints
  async getPayments(params?: { page?: number; page_size?: number; invoice_id?: string; date_from?: string; date_to?: string }) {
    return this.get('/payments', params);
  }

  async createPayment(data: any) {
    return this.post('/payments', data);
  }

  async reconcilePayment(id: string, clearance_date?: string) {
    return this.patch(`/payments/${id}/reconcile`, { clearance_date });
  }

  // Return endpoints
  async getReturns(params?: { page?: number; page_size?: number; status?: string; retailer_id?: string; date_from?: string; date_to?: string }) {
    return this.get('/returns', params);
  }

  async getReturn(id: string) {
    return this.get<{ return: any }>(`/returns/${id}`);
  }

  async createReturn(data: any) {
    return this.post('/returns', data);
  }

  async processReturn(id: string, data: { action: 'approve' | 'reject'; items: any[]; processor_notes?: string }) {
    return this.post(`/returns/${id}/process`, data);
  }

  async inspectReturn(id: string, data: { passed: boolean; notes?: string }) {
    return this.post(`/returns/${id}/inspect`, data);
  }

  async receiveReturn(id: string) {
    return this.post(`/returns/${id}/receive`);
  }

  // Credit Note endpoints
  async getCreditNotes(params?: { invoice_id?: string; retailer_id?: string }) {
    return this.get('/credit-notes', params);
  }

  async createCreditNoteFromReturn(returnRequestId: string) {
    return this.post(`/credit-notes/from-return/${returnRequestId}`);
  }

  // E-Way Bill endpoints
  async getEwayBills(params?: { status?: string; date_from?: string; date_to?: string }) {
    return this.get('/eway-bills', params);
  }

  async createEwayBill(data: any) {
    return this.post('/eway-bills', data);
  }

  async generateEwayBill(id: string) {
    return this.post(`/eway-bills/${id}/generate`);
  }

  async cancelEwayBill(id: string, reason: string) {
    return this.post(`/eway-bills/${id}/cancel`, { reason });
  }

  // Ledger endpoints
  async getRetailerLedger(retailerId: string, params?: { date_from?: string; date_to?: string; entry_type?: string }) {
    return this.get(`/ledger/retailer/${retailerId}`, params);
  }

  async getLedgerEntries(retailerId: string, params?: { page?: number; page_size?: number; date_from?: string; date_to?: string; entry_type?: string }) {
    return this.get(`/ledger/retailer/${retailerId}/entries`, params);
  }

  async recomputeLedger(retailerId: string) {
    return this.post(`/ledger/retailer/${retailerId}/recompute`);
  }

  // Dashboard endpoints
  async getDistributorDashboard() {
    return this.get('/dashboard/distributor');
  }

  async getRetailerDashboard() {
    return this.get('/dashboard/retailer');
  }

  async getSalesSummary(dateFrom: string, dateTo: string, groupBy: 'day' | 'week' | 'month' = 'day') {
    return this.get('/dashboard/sales-summary', { date_from: dateFrom, date_to: dateTo, group_by: groupBy });
  }

  async getTopProducts(dateFrom: string, dateTo: string, limit: number = 10) {
    return this.get('/dashboard/top-products', { date_from: dateFrom, date_to: dateTo, limit });
  }

  async getTopRetailers(dateFrom: string, dateTo: string, limit: number = 10) {
    return this.get('/dashboard/top-retailers', { date_from: dateFrom, date_to: dateTo, limit });
  }

  // Picking endpoints
  async getOrdersReadyForPicking(warehouseId?: string) {
    return this.get('/picking/orders-ready', { warehouse_id: warehouseId });
  }

  async startPicking(orderId: string) {
    return this.post(`/picking/${orderId}/start`);
  }

  async completePicking(orderId: string, packedItems: any[]) {
    return this.post(`/picking/${orderId}/complete`, { packed_items: packedItems });
  }

  async getPickingSlip(orderId: string) {
    return this.get(`/picking/${orderId}/slip`);
  }
}

export const api = new ApiService();