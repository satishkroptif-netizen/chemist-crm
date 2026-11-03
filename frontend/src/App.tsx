import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';
import { LoginPage } from './pages/LoginPage';
import { DistributorLayout } from './layouts/DistributorLayout';
import { RetailerLayout } from './layouts/RetailerLayout';
import { AdminLayout } from './layouts/AdminLayout';
import { LoadingSpinner } from './components/ui/LoadingSpinner';

function PrivateRoute({ children, allowedRoles }: { children: React.ReactNode; allowedRoles?: string[] }) {
  const { user, isLoading, hasRole } = useAuth();
  
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }
  
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  
  if (allowedRoles && !hasRole(allowedRoles as any)) {
    return <Navigate to="/unauthorized" replace />;
  }
  
  return <>{children}</>;
}

function AppRoutes() {
  const { user, isLoading } = useAuth();
  
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    );
  }
  
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      
      {/* Admin Routes */}
      <Route 
        element={
          <PrivateRoute allowedRoles={['super_admin']}>
            <AdminLayout />
          </PrivateRoute>
        } 
      >
        <Route path="/admin" element={<Navigate to="/admin/dashboard" replace />} />
        <Route path="/admin/dashboard" element={<div>Admin Dashboard</div>} />
        <Route path="/admin/distributors" element={<div>Distributors</div>} />
        <Route path="/admin/users" element={<div>Users</div>} />
      </Route>
      
      {/* Distributor Routes */}
      <Route 
        element={
          <PrivateRoute allowedRoles={['distributor_admin', 'distributor_staff', 'super_admin']}>
            <DistributorLayout />
          </PrivateRoute>
        } 
      >
        <Route path="/distributor" element={<Navigate to="/distributor/dashboard" replace />} />
        <Route path="/distributor/dashboard" element={<div>Distributor Dashboard</div>} />
        <Route path="/distributor/retailers" element={<div>Retailers</div>} />
        <Route path="/distributor/products" element={<div>Products</div>} />
        <Route path="/distributor/orders" element={<div>Orders</div>} />
        <Route path="/distributor/invoices" element={<div>Invoices</div>} />
        <Route path="/distributor/payments" element={<div>Payments</div>} />
        <Route path="/distributor/returns" element={<div>Returns</div>} />
        <Route path="/distributor/ledger" element={<div>Ledger</div>} />
        <Route path="/distributor/inventory" element={<div>Inventory</div>} />
        <Route path="/distributor/pricing" element={<div>Pricing Schemes</div>} />
        <Route path="/distributor/warehouses" element={<div>Warehouses</div>} />
        <Route path="/distributor/reports" element={<div>Reports</div>} />
      </Route>
      
      {/* Retailer Routes */}
      <Route 
        element={
          <PrivateRoute allowedRoles={['retailer_admin', 'retailer_staff']}>
            <RetailerLayout />
          </PrivateRoute>
        } 
      >
        <Route path="/retailer" element={<Navigate to="/retailer/dashboard" replace />} />
        <Route path="/retailer/dashboard" element={<div>Retailer Dashboard</div>} />
        <Route path="/retailer/catalog" element={<div>Product Catalog</div>} />
        <Route path="/retailer/orders" element={<div>My Orders</div>} />
        <Route path="/retailer/invoices" element={<div>My Invoices</div>} />
        <Route path="/retailer/returns" element={<div>Returns</div>} />
        <Route path="/retailer/ledger" element={<div>Ledger</div>} />
      </Route>
      
      <Route path="/unauthorized" element={<div className="min-h-screen flex items-center justify-center">Unauthorized</div>} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

export default function App() {
  return <AppRoutes />;
}