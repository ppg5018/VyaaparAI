'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { useAuth } from './auth-context';
import { getBusinessByUser } from './api';

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

  // Resolve business: localStorage cache first, then backend (source of truth)
  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      setBusinessIdState(null);
      setBizLoading(false);
      return;
    }
    const stored = localStorage.getItem(storageKey(user.id));
    if (stored) {
      setBusinessIdState(stored);
      setBizLoading(false);
      return;
    }
    let cancelled = false;
    setBizLoading(true);
    getBusinessByUser(user.id)
      .then((biz) => {
        if (cancelled) return;
        if (biz) {
          localStorage.setItem(storageKey(user.id), biz.business_id);
          setBusinessIdState(biz.business_id);
        } else {
          setBusinessIdState(null);
        }
      })
      .finally(() => {
        if (!cancelled) setBizLoading(false);
      });
    return () => { cancelled = true; };
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
