import { useEffect, useState } from "react"
import type { ReactNode } from "react"

import type { MnemosyneAPI } from "~lib/api"
import type { ProfileItem, UserSettings } from "~lib/types"

export function SettingsPage({ api }: { api: MnemosyneAPI }) {
  const [settings, setSettings] = useState<UserSettings | null>(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getSettings().then(setSettings)
  }, [api])

  if (!settings)
    return (
      <div className="flex flex-1 items-center justify-center font-body-md text-on-surface-variant">Loading…</div>
    )

  const update = (patch: Partial<UserSettings>) => setSettings({ ...settings, ...patch })
  const save = async () => {
    setSaving(true)
    await api.updateSettings(settings)
    setSaving(false)
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      <section className="flex-1 overflow-y-auto p-xl">
        <div className="mx-auto max-w-2xl">
          <div className="mb-lg">
            <h2 className="mb-xs font-headline-lg text-headline-lg text-on-surface">Settings</h2>
            <p className="font-body-sm text-body-sm text-on-surface-variant">Configure persistent state and memory extraction parameters.</p>
          </div>

          <div className="space-y-md">
            <AboutMe api={api} />

            <Panel title="Capture">
              <Toggle label="Capture enabled" value={settings.capture_enabled} onChange={(v) => update({ capture_enabled: v })} />
              <Toggle label="Sensitive data filter" value={settings.sensitive_data_filter} onChange={(v) => update({ sensitive_data_filter: v })} />
              <Toggle label="LLM extraction (Ollama)" value={settings.llm_extraction_enabled} onChange={(v) => update({ llm_extraction_enabled: v })} />
            </Panel>

            <Panel title="Context Injection">
              <Slider
                label="Token budget"
                value={settings.token_budget}
                display={String(settings.token_budget)}
                min={500}
                max={4000}
                step={100}
                onChange={(v) => update({ token_budget: v })}
              />
              <p className="mt-xs font-body-sm text-body-sm text-on-surface-variant">Maximum tokens allocated for persistent memory injection per query.</p>
            </Panel>

            <Panel title="Memory Capture Routing">
              <Slider
                label="Auto-commit threshold"
                value={settings.auto_commit_threshold}
                display={settings.auto_commit_threshold.toFixed(2)}
                min={0.5}
                max={0.95}
                step={0.05}
                onChange={(v) => update({ auto_commit_threshold: v })}
              />
              <Slider
                label="Min confidence score"
                value={settings.min_confidence}
                display={settings.min_confidence.toFixed(2)}
                min={0.3}
                max={0.8}
                step={0.05}
                onChange={(v) => update({ min_confidence: v })}
              />
              <p className="border-l-2 border-primary bg-primary/5 py-xs pl-sm font-body-sm text-body-sm text-on-surface-variant">
                At/above the auto-commit threshold a memory is saved straight away; below min confidence it is discarded; in between it goes to the review queue.
              </p>
            </Panel>

            <Panel title="Privacy">
              <div className="flex items-center justify-between">
                <div>
                  <span className="block font-body-md text-body-md text-on-surface">Cloud LLM processing</span>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">Send sanitized logs to external providers for synthesis.</p>
                </div>
                <ToggleInput value={settings.cloud_fallback_enabled} onChange={(v) => update({ cloud_fallback_enabled: v })} label="Cloud LLM processing" />
              </div>
              <div className="flex items-start gap-sm border border-outline-variant bg-surface-container-highest/30 p-sm">
                <span className="material-symbols-outlined scale-75 text-primary">lock</span>
                <span className="font-body-sm text-body-sm leading-tight text-on-surface-variant">
                  All data is encrypted with AES-256 at rest. Mnemosyne makes no external API calls by default.
                </span>
              </div>
            </Panel>

            <WorkspaceMaintenance api={api} />

            <div className="flex items-center justify-end gap-md pt-lg">
              <span className={`flex items-center gap-xs font-body-sm text-body-sm text-emerald-400 transition-opacity ${saved ? "opacity-100" : "opacity-0"}`}>
                <span className="material-symbols-outlined text-[14px]">check_circle</span>
                Changes saved
              </span>
              <button
                onClick={save}
                disabled={saving}
                className="flex items-center gap-sm bg-primary px-xl py-sm font-label-caps text-label-caps uppercase text-on-primary transition-all hover:opacity-90 active:scale-95 disabled:opacity-70">
                {saving && <span className="material-symbols-outlined animate-spin text-[14px]">sync</span>}
                {saving ? "Saving…" : "Save Settings"}
              </button>
            </div>
          </div>

          {/* Technical aesthetic decoration. */}
          <div className="mt-xl grid grid-cols-3 gap-md opacity-20">
            <div className="relative h-24 overflow-hidden border border-outline-variant bg-surface-container">
              <div className="absolute inset-0 bg-gradient-to-t from-primary/10 to-transparent" />
              <div className="p-xs font-code-md text-[8px] uppercase">Node_Status_01</div>
            </div>
            <div className="relative h-24 overflow-hidden border border-outline-variant bg-surface-container">
              <div className="absolute left-0 top-1/2 h-px w-full bg-primary" />
              <div className="p-xs font-code-md text-[8px] uppercase">Bus_Traffic</div>
            </div>
            <div className="relative h-24 overflow-hidden border border-outline-variant bg-surface-container">
              <div className="flex h-full items-end gap-[1px]">
                <div className="h-2/3 w-1 bg-primary" />
                <div className="h-1/2 w-1 bg-primary" />
                <div className="h-5/6 w-1 bg-primary" />
                <div className="h-1/3 w-1 bg-primary" />
              </div>
              <div className="absolute left-0 top-0 p-xs font-code-md text-[8px] uppercase">Entropy_Dist</div>
            </div>
          </div>
        </div>
      </section>

      {/* System Health Panel */}
      <aside className="hidden w-[320px] shrink-0 flex-col space-y-md border-l border-outline-variant bg-surface-container-low p-md lg:flex">
        <header className="border-b border-outline-variant pb-xs font-label-caps text-label-caps uppercase tracking-widest text-on-surface-variant">System Health</header>
        <div className="relative overflow-hidden border border-outline-variant bg-surface-container-lowest p-sm">
          <div className="mb-xs flex items-center justify-between">
            <span className="font-body-sm text-body-sm text-on-surface">Capture</span>
            <span className="font-code-md text-code-md text-primary">{settings.capture_enabled ? "ON" : "OFF"}</span>
          </div>
          <div className="h-1 w-full bg-surface-container-highest">
            <div className="h-full bg-primary" style={{ width: settings.capture_enabled ? "100%" : "0%" }} />
          </div>
        </div>
        <div className="space-y-xs">
          <header className="font-label-caps text-[9px] uppercase text-on-surface-variant opacity-60">Extraction Mode</header>
          <div className="border-l-2 border-primary bg-surface-container-highest/20 p-sm">
            <div className="mb-base font-body-md text-body-md text-on-surface">{settings.llm_extraction_enabled ? "LLM (Ollama)" : "Rule-based"}</div>
            <div className="flex items-center gap-base font-body-sm text-body-sm text-on-surface-variant">
              {settings.cloud_fallback_enabled ? "Cloud fallback enabled" : "Fully local"}
            </div>
          </div>
        </div>
      </aside>
    </div>
  )
}

function AboutMe({ api }: { api: MnemosyneAPI }) {
  const [items, setItems] = useState<ProfileItem[]>([])
  const [draft, setDraft] = useState("")

  const load = () => {
    api.getProfile().then((r) => setItems(r.items)).catch(() => {})
  }
  useEffect(load, [api])

  const add = async () => {
    const t = draft.trim()
    if (!t) return
    await api.addProfile(t)
    setDraft("")
    load()
  }
  const remove = async (id: string) => {
    await api.deleteProfile(id)
    load()
  }

  return (
    <Panel title="About Me — injected into every chat">
      <p className="font-body-sm text-body-sm text-on-surface-variant">
        Durable facts about you (role, stack, preferences). Added here or learned automatically, and sent with every project's context so you never re-explain who you are.
      </p>
      <div className="space-y-xs">
        {items.map((it) => (
          <div key={it.id} className="flex items-center justify-between gap-sm border border-outline-variant bg-surface-container-low p-sm">
            <span className="font-body-sm text-body-sm text-on-surface">{it.content}</span>
            <div className="flex shrink-0 items-center gap-sm">
              <span className="font-label-caps text-[9px] uppercase text-outline">{it.source === "model" ? "auto" : "you"}</span>
              <button onClick={() => remove(it.id)} aria-label="Remove" className="text-on-surface-variant transition-colors hover:text-error">
                <span className="material-symbols-outlined !text-[16px]">close</span>
              </button>
            </div>
          </div>
        ))}
        {items.length === 0 && (
          <p className="font-body-sm text-body-sm text-outline">Nothing yet — e.g. "Junior backend dev, prefer Python/FastAPI, like tradeoff explanations."</p>
        )}
      </div>
      <div className="flex gap-sm">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="Add a fact about you…"
          className="h-9 flex-1 border border-outline-variant bg-surface-container px-md font-body-sm text-body-sm text-on-surface outline-none transition-colors focus:border-primary"
        />
        <button onClick={add} className="h-9 bg-primary px-md font-label-caps text-label-caps uppercase text-on-primary transition-opacity hover:opacity-90">Add</button>
      </div>
    </Panel>
  )
}

function WorkspaceMaintenance({ api }: { api: MnemosyneAPI }) {
  const [busy, setBusy] = useState(false)
  const [report, setReport] = useState<string | null>(null)

  const run = async () => {
    if (!confirm("Merge same-named duplicate workspaces and delete empty ones? Memories are moved into the kept workspace. This can't be undone.")) return
    setBusy(true)
    setReport(null)
    try {
      const r = await api.cleanupWorkspaces()
      const m = r.merged.length
      const d = r.deleted_empty.length
      setReport(`Merged ${m} duplicate${m === 1 ? "" : "s"}, removed ${d} empty workspace${d === 1 ? "" : "s"}. Reload to refresh the list.`)
    } catch {
      setReport("Cleanup failed — is the engine running?")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel title="Workspace Maintenance">
      <p className="font-body-sm text-body-sm text-on-surface-variant">
        Merge duplicate workspaces (same name) and remove empty ones left over from earlier routing issues. Memories are preserved — moved into the kept workspace.
      </p>
      <div className="flex flex-wrap items-center gap-md">
        <button
          onClick={run}
          disabled={busy}
          className="flex items-center gap-sm border border-outline-variant bg-surface-container-highest px-md py-sm font-label-caps text-label-caps uppercase text-on-surface transition-colors hover:border-primary disabled:opacity-50">
          {busy && <span className="material-symbols-outlined animate-spin text-[14px]">sync</span>}
          {busy ? "Cleaning…" : "Clean up workspaces"}
        </button>
        {report && <span className="font-body-sm text-body-sm text-on-surface-variant">{report}</span>}
      </div>
    </Panel>
  )
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="border border-outline-variant bg-surface-container-low p-md">
      <header className="mb-md border-b border-outline-variant pb-sm font-label-caps text-label-caps uppercase tracking-widest text-on-surface-variant">{title}</header>
      <div className="space-y-lg">{children}</div>
    </div>
  )
}

function ToggleInput({ value, onChange, label }: { value: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="custom-toggle">
      <input type="checkbox" aria-label={label} checked={value} onChange={(e) => onChange(e.target.checked)} />
      <span className="slider-toggle" />
    </label>
  )
}

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between">
      <span className="font-body-md text-body-md text-on-surface">{label}</span>
      <ToggleInput value={value} onChange={onChange} label={label} />
    </div>
  )
}

function Slider({
  label,
  value,
  display,
  min,
  max,
  step,
  onChange,
}: {
  label: string
  value: number
  display: string
  min: number
  max: number
  step: number
  onChange: (v: number) => void
}) {
  return (
    <div className="space-y-sm">
      <div className="flex items-center justify-between">
        <span className="font-body-md text-body-md text-on-surface">{label}</span>
        <span className="font-code-md text-code-md text-primary">{display}</span>
      </div>
      <input
        type="range"
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full"
      />
    </div>
  )
}
