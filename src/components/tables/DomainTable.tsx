import { useState, useMemo } from 'react'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table'
import type { ModelInfo, ModelScoreMap } from '../../types/leaderboard'
import ScoreCell from '../ScoreCell'

interface DomainRow {
  domain: string
  [modelId: string]: string | number | undefined
}

interface DomainTableProps {
  byDomain: Record<string, ModelScoreMap>
  models: ModelInfo[]
  title?: string
}

export default function DomainTable({ byDomain, models, title }: DomainTableProps) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [globalFilter, setGlobalFilter] = useState('')

  const rows: DomainRow[] = useMemo(() =>
    Object.entries(byDomain).map(([domain, scores]) => {
      const row: DomainRow = { domain }
      for (const m of models) {
        row[m.id] = scores[m.id]?.percentage
      }
      return row
    }),
  [byDomain, models])

  const col = createColumnHelper<DomainRow>()

  const columns = useMemo(() => [
    col.accessor('domain', {
      header: 'Domain / Industry',
      cell: info => (
        <span className="font-medium text-sm" style={{ color: 'var(--text-primary)' }}>
          {info.getValue() as string}
        </span>
      ),
      enableSorting: false,
      size: 260,
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
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  })

  return (
    <div>
      {title && (
        <h3 className="font-semibold text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
          {title}
        </h3>
      )}
      <div className="flex mb-3">
        <input
          value={globalFilter}
          onChange={e => setGlobalFilter(e.target.value)}
          placeholder="Filter domains..."
          className="px-3 py-1.5 text-sm rounded border outline-none w-52"
          style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
          }}
        />
      </div>
      <div className="card overflow-x-auto">
        <table className="ocb-table">
          <thead>
            {table.getHeaderGroups().map(hg => (
              <tr key={hg.id}>
                {hg.headers.map(header => (
                  <th
                    key={header.id}
                    className={header.column.id === 'domain' ? 'sticky-col' : ''}
                    onClick={header.column.getToggleSortingHandler()}
                    style={{ minWidth: header.column.id === 'domain' ? 220 : 120 }}
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
                    className={cell.column.id === 'domain' ? 'sticky-col' : ''}
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
            No domains match your filter.
          </div>
        )}
      </div>
    </div>
  )
}
