export default function Aurora() {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        pointerEvents: 'none',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          width: 600,
          height: 600,
          borderRadius: '50%',
          background: 'rgba(139,111,255,0.18)',
          filter: 'blur(80px)',
          top: -200,
          left: -100,
          animation: 'drift 22s ease-in-out infinite',
        }}
      />
      <div
        style={{
          position: 'absolute',
          width: 500,
          height: 500,
          borderRadius: '50%',
          background: 'rgba(245,166,35,0.12)',
          filter: 'blur(80px)',
          bottom: -150,
          right: -100,
          animation: 'drift 28s ease-in-out infinite reverse',
        }}
      />
      <div
        style={{
          position: 'absolute',
          width: 400,
          height: 400,
          borderRadius: '50%',
          background: 'rgba(16,217,160,0.1)',
          filter: 'blur(80px)',
          top: '40%',
          left: '40%',
          animation: 'drift 18s ease-in-out infinite',
          animationDelay: '-9s',
        }}
      />
    </div>
  );
}
