'use client';

import { useEffect, useState } from 'react';

/**
 * Single source of truth for breakpoint logic across the app.
 * Mobile  < 640px  · Tablet 640–1023px · Desktop ≥ 1024px
 */
export function useViewport() {
  const [width, setWidth] = useState<number>(
    typeof window !== 'undefined' ? window.innerWidth : 1200,
  );

  useEffect(() => {
    const onResize = () => setWidth(window.innerWidth);
    onResize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  return {
    width,
    isMobile:  width < 640,
    isTablet:  width >= 640 && width < 1024,
    isDesktop: width >= 1024,
  };
}
