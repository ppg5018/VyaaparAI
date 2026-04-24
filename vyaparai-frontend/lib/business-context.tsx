'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { useAuth } from './auth-context';

interface BusinessContextValue {
  businessId: string | null;
  bizLoading: boolean;
  setBusinessId: (id: string) => void;
  clearBusinessId: () => void;
}

const BusinessContext = createContext<BusinessContextValue>({
  businessId: null,
  bizLoading: true,
  setBusinessId: () => {},
  clearBusinessId: () => {},
});

function storageKey(userId: string) {
  return `vyapaar-business-id-${userId}`;
}

export function BusinessProvider({ children }: { children: React.ReactNode }) {
  const { user, loading: authLoading } = useAuth();
  const [businessId, setBusinessIdState] = useState<string | null>(null);
  const [bizLoading, setBizLoading]      = useState(true);

  // Re-read from localStorage once auth has resolved and user is known
  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      setBusinessIdState(null);
      setBizLoading(false);
      return;
    }
    const stored = localStorage.getItem(storageKey(user.id));
    setBusinessIdState(stored ?? null);
    setBizLoading(false);
  }, [authLoading, user?.id]);

  const setBusinessId = (id: string) => {
    if (!user) return;
    localStorage.setItem(storageKey(user.id), id);
    setBusinessIdState(id);
  };

  const clearBusinessId = () => {
    if (!user) return;
    localStorage.removeItem(storageKey(user.id));
    setBusinessIdState(null);
  };

  return (
    <BusinessContext.Provider value={{ businessId, bizLoading, setBusinessId, clearBusinessId }}>
      {children}
    </BusinessContext.Provider>
  );
}

export function useBusinessId() {
  return useContext(BusinessContext);
}
