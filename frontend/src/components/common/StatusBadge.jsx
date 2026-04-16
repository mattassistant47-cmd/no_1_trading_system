import clsx from 'clsx'

export default function StatusBadge({ status, label }) {
  const statusStyles = {
    success: 'bg-neon-green/20 text-neon-green border-neon-green/30',
    warning: 'bg-yellow-500/20 text-yellow-500 border-yellow-500/30',
    error: 'bg-neon-red/20 text-neon-red border-neon-red/30',
    neutral: 'bg-surface text-muted border-grid',
  }

  return (
    <div className={clsx(
      'flex items-center gap-2 px-3 py-1 rounded border text-xs font-semibold',
      statusStyles[status] || statusStyles.neutral
    )}>
      <div className={clsx(
        'w-2 h-2 rounded-full',
        status === 'success' ? 'bg-neon-green' :
        status === 'warning' ? 'bg-yellow-500' :
        status === 'error' ? 'bg-neon-red' :
        'bg-muted'
      )} />
      {label}
    </div>
  )
}
