import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User, UserRole, Token } from '../types';
import { api } from '../services/api';

interface AuthContextType {
  user: User | null;
  token: Token | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  hasRole: (roles: UserRole[]) => boolean;
  isDistributor: boolean;
  isRetailer: boolean;
  isSuperAdmin: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<Token | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    initAuth();
  }, []);

  const initAuth = async () => {
    const storedToken = localStorage.getItem('access_token');
    const storedRefreshToken = localStorage.getItem('refresh_token');
    
    if (storedToken && storedRefreshToken) {
      try {
        api.setTokens({
          access_token: storedToken,
          refresh_token: storedRefreshToken,
          token_type: 'bearer',
          expires_in: 604800,
        });
        await refreshUser();
      } catch {
        api.clearAuth();
      }
    }
    setIsLoading(false);
  };

  const refreshUser = async () => {
    try {
      const userData = await api.getMe();
      setUser(userData);
    } catch {
      setUser(null);
    }
  };

  const login = async (email: string, password: string) => {
    const tokenData = await api.login(email, password);
    setToken(tokenData);
    await refreshUser();
  };

  const logout = async () => {
    await api.logout();
    setUser(null);
    setToken(null);
  };

  const hasRole = (roles: UserRole[]) => {
    return user ? roles.includes(user.role) : false;
  };

  const isDistributor = hasRole(['distributor_admin', 'distributor_staff']);
  const isRetailer = hasRole(['retailer_admin', 'retailer_staff']);
  const isSuperAdmin = hasRole(['super_admin']);

  return (
    <AuthContext.Provider value={{
      user,
      token,
      isLoading,
      login,
      logout,
      refreshUser,
      hasRole,
      isDistributor,
      isRetailer,
      isSuperAdmin,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}