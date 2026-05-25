import { useEffect, useState } from "react"
import type { ReactNode } from "react"

import type { MnemosyneAPI } from "~lib/api"
import type { UserSettings } from "~lib/types"

export function SettingsPage({ api }: { api: MnemosyneAPI }) {
  const [settings, setSettings] = useState<UserSettings | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.getSettings().then(setSettings)
  }, [api])

  if (!settings) return <p className="p-8 text-sm text-text-secondary">Loading…</p>

  const update = (patch: Partial<UserSettings>) => setSettings({ ...settings, ...patch })
  const save = async () => {
    await api.updateSettings(settings)
    setSaved(true)
    setTimeout(() => setSaved(false), 1500)
  }

  return (
    <div className="max-w-2xl space-y-6 p-8">
      <h1 className="text-2xl font-bold">Settings</h1>

      <Section title="Capture">
        <Toggle label="Capture enabled" value={settings.capture_enabled} onChange={(v) => update({ capture_enabled: v })} />
        <Toggle label="Sensitive data filter" value={settings.sensitive_data_filter} onChange={(v) => update({ sensitive_data_filter: v })} />
        <Toggle label="LLM extraction (Ollama)" value={settings.llm_extraction_enabled} onChange={(v) => update({ llm_extraction_enabled: v })} />
      </Section>

      <Section title="Context Injection">
        <Slider label="Token budget" value={settings.token_budget} min={500} max={4000} step={100} onChange={(v) => update({ token_budget: v })} />
      </Section>

      <Section title="Memory Capture Routing">
        <Slider label="Auto-commit threshold (≥ saves straight to memory)" value={settings.auto_commit_threshold} min={0.5} max={0.95} step={0.05} onChange={(v) => update({ auto_commit_threshold: v })} />
        <Slider label="Min confidence (below this is discarded; between the two → pending review)" value={settings.min_confidence} min={0.3} max={0.8} step={0.05} onChange={(v) => update({ min_confidence: v })} />
        <p className="text-xs text-text-secondary">Lower the top slider to capture more automatically; raise it to send more to the review queue.</p>
      </Section>

      <Section title="Privacy">
        <Toggle label="Cloud LLM fallback (sends data externally)" value={settings.cloud_fallback_enabled} onChange={(v) => update({ cloud_fallback_enabled: v })} />
        <p className="text-xs text-text-secondary">Encryption: AES-256 at rest · External API calls: 0 by default</p>
      </Section>

      <button onClick={save} className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white">
        {saved ? "Saved ✓" : "Save Settings"}
      </button>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-bg-secondary p-5">
      <h2 className="mb-3 text-sm font-semibold uppercase text-text-secondary">{title}</h2>
      <div className="space-y-3">{children}</div>
    </div>
  )
}

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between text-sm">
      <span>{label}</span>
      <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} />
    </label>
  )
}

function Slider({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void }) {
  return (
    <label className="block text-sm">
      <div className="mb-1 flex justify-between">
        <span>{label}</span>
        <span className="text-text-secondary">{value}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full" />
    </label>
  )
}
