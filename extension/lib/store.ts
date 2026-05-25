// Zustand store for extension UI state (Doc 11).

import { create } from "zustand"

import type { Workspace } from "~lib/types"

interface MnemosyneState {
  engineOnline: boolean
  engineVersion: string | null
  activeWorkspace: Workspace | null
  workspaces: Workspace[]
  captureEnabled: boolean
  incognito: boolean
  pendingReviewCount: number
  activeTab: "memory" | "graph" | "audit" | "search"

  setEngine: (online: boolean, version?: string) => void
  setActiveWorkspace: (ws: Workspace | null) => void
  setWorkspaces: (ws: Workspace[]) => void
  toggleCapture: () => void
  toggleIncognito: () => void
  setPendingCount: (n: number) => void
  setActiveTab: (t: MnemosyneState["activeTab"]) => void
}

export const useStore = create<MnemosyneState>((set) => ({
  engineOnline: false,
  engineVersion: null,
  activeWorkspace: null,
  workspaces: [],
  captureEnabled: true,
  incognito: false,
  pendingReviewCount: 0,
  activeTab: "memory",

  setEngine: (online, version) => set({ engineOnline: online, engineVersion: version ?? null }),
  setActiveWorkspace: (ws) => set({ activeWorkspace: ws }),
  setWorkspaces: (ws) => set({ workspaces: ws }),
  toggleCapture: () => set((s) => ({ captureEnabled: !s.captureEnabled })),
  toggleIncognito: () => set((s) => ({ incognito: !s.incognito })),
  setPendingCount: (n) => set({ pendingReviewCount: n }),
  setActiveTab: (t) => set({ activeTab: t }),
}))
