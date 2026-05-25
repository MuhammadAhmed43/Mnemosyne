import type { Workspace } from "~lib/types"

interface Props {
  workspaces: Workspace[]
  active: Workspace | null
  onChange: (ws: Workspace) => void
}

export function WorkspaceSelector({ workspaces, active, onChange }: Props) {
  return (
    <select
      className="w-full rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary"
      value={active?.id ?? ""}
      onChange={(e) => {
        const ws = workspaces.find((w) => w.id === e.target.value)
        if (ws) onChange(ws)
      }}
    >
      {!active && <option value="">Select a workspace…</option>}
      {workspaces.map((w) => (
        <option key={w.id} value={w.id}>
          {w.icon} {w.name} ({w.node_count})
        </option>
      ))}
    </select>
  )
}
