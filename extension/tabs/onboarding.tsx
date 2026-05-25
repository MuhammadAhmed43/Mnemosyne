import { useEffect, useState } from "react"

import { MnemosyneAPI } from "~lib/api"

import "~style.css"

type Step = "welcome" | "engine" | "workspace" | "ready"

function Onboarding() {
  const [step, setStep] = useState<Step>("welcome")
  const [wsName, setWsName] = useState("")

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-primary text-text-primary">
      <div className="w-[520px]">
        {step === "welcome" && <Welcome onNext={() => setStep("engine")} />}
        {step === "engine" && <EngineCheck onNext={() => setStep("workspace")} />}
        {step === "workspace" && <WorkspaceCreate onCreated={(n) => { setWsName(n); setStep("ready") }} />}
        {step === "ready" && <Ready name={wsName} />}
      </div>
    </div>
  )
}

function Welcome({ onNext }: { onNext: () => void }) {
  return (
    <div className="space-y-6 text-center">
      <div className="text-5xl">🧠</div>
      <h1 className="text-3xl font-bold">Mnemosyne</h1>
      <p className="text-lg text-text-secondary">AI that remembers everything you build.</p>
      <div className="border-t border-border" />
      <p className="text-text-secondary">
        You explain your project once. Every AI conversation after that starts with full context — automatically.
      </p>
      <button onClick={onNext} className="rounded-lg bg-accent px-8 py-3 text-lg font-medium text-white">
        Get Started →
      </button>
    </div>
  )
}

function EngineCheck({ onNext }: { onNext: () => void }) {
  const [status, setStatus] = useState<"checking" | "found" | "not_found">("checking")

  useEffect(() => {
    const api = new MnemosyneAPI("")
    const tick = async () => {
      const health = await api.probe()
      if (health) {
        // Background also pairs; ensure a token is present before continuing.
        setStatus("found")
        return true
      }
      setStatus("not_found")
      return false
    }
    void tick()
    const id = setInterval(() => void tick().then((ok) => ok && clearInterval(id)), 3000)
    return () => clearInterval(id)
  }, [])

  if (status === "found") {
    return (
      <div className="space-y-4 text-center">
        <div className="text-4xl">✓</div>
        <h2 className="text-xl font-semibold">Engine running · v1.0.0</h2>
        <p className="text-text-secondary">Your data is stored locally — nothing leaves your device.</p>
        <button onClick={onNext} className="rounded-lg bg-accent px-8 py-3 text-white">Continue →</button>
      </div>
    )
  }
  return (
    <div className="space-y-4 text-center">
      <h2 className="text-xl font-semibold">Install the local engine</h2>
      <p className="text-text-secondary">
        Mnemosyne runs entirely on your machine. Download and run the engine, then this page updates automatically.
      </p>
      <div className="flex items-center justify-center gap-2 text-sm text-text-tertiary">
        <span className="h-2 w-2 animate-pulse rounded-full bg-accent" /> Waiting for engine…
      </div>
    </div>
  )
}

function WorkspaceCreate({ onCreated }: { onCreated: (name: string) => void }) {
  const [description, setDescription] = useState("")
  const [name, setName] = useState("")
  const [busy, setBusy] = useState(false)

  const suggest = async () => {
    if (description.length < 8) return
    const { auth_token } = await chrome.storage.local.get("auth_token")
    const api = new MnemosyneAPI(auth_token ?? "")
    await api.probe()
    // Use the engine's heuristic name suggester via a direct call.
    try {
      const r = await fetch(`http://localhost:7432/api/v1/onboarding/suggest-name`, {
        method: "POST",
        headers: { Authorization: `Bearer ${auth_token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ description }),
      })
      if (r.ok) setName((await r.json()).suggested_name)
    } catch {
      /* leave name for manual entry */
    }
  }

  const create = async () => {
    setBusy(true)
    const { auth_token } = await chrome.storage.local.get("auth_token")
    const api = new MnemosyneAPI(auth_token ?? "")
    await api.probe()
    await api.createWorkspace({ name: name || "My Workspace", description })
    onCreated(name || "My Workspace")
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">What are you working on right now?</h2>
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        onBlur={suggest}
        placeholder='e.g. "a blind navigation startup", "my ML research"'
        className="h-24 w-full rounded-lg border border-border bg-bg-tertiary p-3"
      />
      <div>
        <label className="text-sm text-text-secondary">Give it a name</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Workspace name"
          className="mt-1 w-full rounded-lg border border-border bg-bg-tertiary px-4 py-3"
        />
      </div>
      <button onClick={create} disabled={busy || !name.trim()} className="w-full rounded-lg bg-accent py-3 font-medium text-white disabled:opacity-40">
        {busy ? "Creating…" : "Create Workspace →"}
      </button>
    </div>
  )
}

function Ready({ name }: { name: string }) {
  return (
    <div className="space-y-6 text-center">
      <div className="text-4xl">✓</div>
      <h2 className="text-xl font-semibold">"{name}" ready</h2>
      <p className="text-text-secondary">Now go talk to your AI. Mnemosyne will learn in the background.</p>
      <a href="https://claude.ai" target="_blank" rel="noreferrer" className="inline-block rounded-lg bg-accent px-8 py-3 font-medium text-white">
        → Open Claude.ai
      </a>
    </div>
  )
}

export default Onboarding
