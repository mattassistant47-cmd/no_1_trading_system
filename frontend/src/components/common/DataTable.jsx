import clsx from 'clsx'
import { ChevronUp, ChevronDown } from 'lucide-react'

export default function DataTable({
  columns,
  data,
  sortConfig,
  onSort,
  loading,
  emptyMessage = 'No data available',
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b border-grid">
          <tr className="text-muted">
            {columns.map((col) => (
              <th
                key={col.key}
                onClick={() => onSort?.(col.key)}
                className={clsx(
                  'text-left py-3 px-2',
                  col.sortable && 'cursor-pointer hover:text-neon-cyan transition'
                )}
                style={{ textAlign: col.align || 'left' }}
              >
                <div className="flex items-center gap-2">
                  {col.label}
                  {col.sortable && sortConfig?.key === col.key && (
                    sortConfig.direction === 'asc' ? (
                      <ChevronUp className="w-4 h-4" />
                    ) : (
                      <ChevronDown className="w-4 h-4" />
                    )
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={columns.length} className="text-center py-4 text-muted">
                Loading...
              </td>
            </tr>
          ) : data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="text-center py-4 text-muted">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((row, i) => (
              <tr
                key={i}
                className="border-b border-grid hover:bg-surface/50 transition"
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className="py-3 px-2"
                    style={{ textAlign: col.align || 'left' }}
                  >
                    {col.render
                      ? col.render(row[col.key], row)
                      : row[col.key]}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
