/**
 * StatusIndicator — animated dot + label for repository status.
 * Status values: pending | analyzing | ready | error
 */

type Status = 'pending' | 'analyzing' | 'ready' | 'error';

interface StatusIndicatorProps {
  status: Status | string;
  showLabel?: boolean;
}

const STATUS_CONFIG: Record<Status, { color: string; label: string; pulse?: boolean }> = {
  pending: { color: '#F59E0B', label: 'Pending' },
  analyzing: { color: 'var(--secondary)', label: 'Analyzing', pulse: true },
  ready: { color: 'var(--success)', label: 'Ready' },
  error: { color: 'var(--error)', label: 'Error' },
};

const DEFAULT_CONFIG = { color: 'var(--text-tertiary)', label: 'Unknown' };

export function StatusIndicator({ status, showLabel = true }: StatusIndicatorProps) {
  const config = STATUS_CONFIG[status as Status] ?? { ...DEFAULT_CONFIG, label: status };
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: config.color,
          display: 'inline-block',
          boxShadow: `0 0 6px ${config.color}`,
          animation: config.pulse ? 'pulse 2s ease-in-out infinite' : 'none',
        }}
      />
      {showLabel && (
        <span style={{ fontSize: 13, color: config.color, fontWeight: 500 }}>
          {config.label}
        </span>
      )}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </span>
  );
}
