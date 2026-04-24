interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  style?: React.CSSProperties;
}

export default function Skeleton({ width, height = 20, borderRadius, style }: SkeletonProps) {
  return (
    <div
      style={{
        background: 'var(--surface2)',
        borderRadius: borderRadius ?? 'var(--r)',
        width: width ?? '100%',
        height,
        overflow: 'hidden',
        position: 'relative',
        flexShrink: 0,
        ...style,
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.07) 50%, transparent 100%)',
          animation: 'shimmer 1.5s ease-in-out infinite',
        }}
      />
    </div>
  );
}
