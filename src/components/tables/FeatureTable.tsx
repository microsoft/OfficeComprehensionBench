import { useState, useMemo } from 'react'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
  type SortingState,
  type PaginationState,
} from '@tanstack/react-table'
import type { ModelInfo, ModelScoreMap } from '../../types/leaderboard'
import ScoreCell from '../ScoreCell'

interface FeatureRow {
  feature: string
  [modelId: string]: string | number | undefined
}

interface FeatureTableProps {
  byFeature: Record<string, ModelScoreMap>
  models: ModelInfo[]
  title?: string
}

export default function FeatureTable({ byFeature, models, title }: FeatureTableProps) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [globalFilter, setGlobalFilter] = useState('')
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 20 })

  const rows: FeatureRow[] = useMemo(() =>
    Object.entries(byFeature).map(([feature, scores]) => {
      const row: FeatureRow = { feature }
      for (const m of models) {
        const v = scores[m.id]?.percentage
        row[m.id] = v
      }
      return row
    }),
  [byFeature, models])

  const col = createColumnHelper<FeatureRow>()

  const columns = useMemo(() => [
    col.accessor('feature', {
      header: 'Feature / Capability',
      cell: info => (
        <span className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>
          {info.getValue() as string}
        </span>
      ),
      enableSorting: false,
      size: 280,
    }),
    ...models.map(m =>
      col.accessor((row) => row[m.id] as number | undefined, {
        id: m.id,
        header: () => (
          <span className="text-[11px] leading-tight block max-w-[120px]">{m.display_name}</span>
        ),
        cell: info => <ScoreCell value={info.getValue()} />,
        sortDescFirst: true,
      })
    ),
  ], [models])

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting, globalFilter, pagination },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  })

  return (
    <div>
      {title && (
        <h3 className="font-semibold text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
          {title}
        </h3>
      )}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <input
          value={globalFilter}
          onChange={e => setGlobalFilter(e.target.value)}
          placeholder="Filter features..."
          className="px-3 py-1.5 text-sm rounded border outline-none w-52"
          style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
          }}
        />
        <span className="text-xs ml-auto" style={{ color: 'var(--text-muted)' }}>
          {table.getFilteredRowModel().rows.length} features
        </span>
      </div>
      <div className="card overflow-x-auto">
        <table className="ocb-table">
          <thead>
            {table.getHeaderGroups().map(hg => (
              <tr key={hg.id}>
                {hg.headers.map(header => (
                  <th
                    key={header.id}
                    className={header.column.id === 'feature' ? 'sticky-col' : ''}
                    onClick={header.column.getToggleSortingHandler()}
                    style={{ minWidth: header.column.id === 'feature' ? 220 : 120 }}
                  >
                    <span className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getCanSort() && (
                        <span className="text-[10px] opacity-50">
                          {{ asc: '↑', desc: '↓' }[header.column.getIsSorted() as string] ?? '↕'}
                        </span>
                      )}
                    </span>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map(row => (
              <tr key={row.id}>
                {row.getVisibleCells().map(cell => (
                  <td
                    key={cell.id}
                    className={cell.column.id === 'feature' ? 'sticky-col' : ''}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {table.getRowModel().rows.length === 0 && (
          <div className="p-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
            No features match your filter.
          </div>
        )}
      </div>

      {/* Pagination */}
      {table.getPageCount() > 1 && (
        <div className="flex items-center justify-between mt-3 text-xs" style={{ color: 'var(--text-secondary)' }}>
          <span>
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
          </span>
          <div className="flex gap-1">
            {[
              { label: '«', fn: () => table.firstPage(),    disabled: !table.getCanPreviousPage() },
              { label: '‹', fn: () => table.previousPage(), disabled: !table.getCanPreviousPage() },
              { label: '›', fn: () => table.nextPage(),     disabled: !table.getCanNextPage() },
              { label: '»', fn: () => table.lastPage(),     disabled: !table.getCanNextPage() },
            ].map(({ label, fn, disabled }) => (
              <button
                key={label}
                onClick={fn}
                disabled={disabled}
                className="w-7 h-7 rounded border text-xs font-bold transition-colors"
                style={{
                  background: 'var(--bg-surface)',
                  borderColor: 'var(--border)',
                  color: disabled ? 'var(--text-muted)' : 'var(--accent)',
                  cursor: disabled ? 'not-allowed' : 'pointer',
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
