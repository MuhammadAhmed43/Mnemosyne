import { useEffect, useState } from "react"

import { MnemosyneAPI } from "~lib/api"

import "~style.css"

type Step = 1 | 2 | 3 | 4

function Onboarding() {
  const [step, setStep] = useState<Step>(1)
  const [wsName, setWsName] = useState("")

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background font-body-md text-on-surface">
      {/* Atmospheric background */}
      <div className="pointer-events-none fixed inset-0 opacity-20">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,_#5856d6_0%,_transparent_50%)]" />
      </div>

      <main className="relative z-10 w-full max-w-[520px] px-md">
        <div className="overflow-hidden rounded-lg bg-surface-container-lowest p-xl">
          {step === 1 && <Welcome onNext={() => setStep(2)} />}
          {step === 2 && <EngineCheck onNext={() => setStep(3)} />}
          {step === 3 && <WorkspaceCreate onCreated={(n) => { setWsName(n); setStep(4) }} />}
          {step === 4 && <Ready name={wsName} />}

          {/* Progress dots */}
          <div className="mt-xl flex justify-center gap-sm">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className={`h-1.5 w-1.5 transition-all duration-300 ${i <= step ? "bg-primary" : "bg-outline-variant"}`} />
            ))}
          </div>
        </div>

        {/* Meta footer */}
        <div className="mt-md flex items-center justify-between px-sm">
          <span className="font-code-md text-[10px] uppercase tracking-widest text-outline opacity-50">Build 1.0.0-stable</span>
          <div className="flex gap-md">
            <span className="cursor-pointer font-code-md text-[10px] uppercase text-outline opacity-50 hover:opacity-100">Docs</span>
            <span className="cursor-pointer font-code-md text-[10px] uppercase text-outline opacity-50 hover:opacity-100">Support</span>
          </div>
        </div>
      </main>
    </div>
  )
}

function Welcome({ onNext }: { onNext: () => void }) {
  return (
    <section className="space-y-lg">
      <div className="flex flex-col items-center text-center">
        <div className="mb-md flex h-16 w-16 items-center justify-center rounded-lg bg-primary-container">
          <span className="material-symbols-outlined text-[32px] text-white" style={{ fontVariationSettings: "'FILL' 1" }}>memory</span>
        </div>
        <h1 className="font-headline-lg text-headline-lg tracking-tighter text-on-surface">Mnemosyne</h1>
        <p className="mt-base font-label-caps text-label-caps uppercase tracking-[0.2em] text-primary">Persistent AI State Engine</p>
      </div>
      <div className="h-px w-full bg-outline-variant" />
      <p className="font-body-md text-body-md leading-relaxed text-on-surface-variant">
        Mnemosyne is a long-term memory layer for your AI workflows. You explain your project once; every AI conversation after that starts with full context — captured, indexed, and recalled automatically.
      </p>
      <button onClick={onNext} className="flex h-8 w-full items-center justify-center bg-primary font-label-caps text-label-caps uppercase text-on-primary transition-opacity hover:opacity-90 active:scale-[0.98]">
        Get Started
      </button>
    </section>
  )
}

function EngineCheck({ onNext }: { onNext: () => void }) {
  const [status, setStatus] = useState<"checking" | "found" | "not_found">("checking")

  useEffect(() => {
    const api = new MnemosyneAPI("")
    const tick = async () => {
      const health = await api.probe()
      if (health) {
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

  const found = status === "found"

  return (
    <section className="space-y-lg">
      <div className="flex items-center justify-between">
        <h2 className="font-headline-md text-headline-md">Install Local Engine</h2>
        <span className="font-code-md text-body-sm text-outline">STP_02</span>
      </div>

      <div className="space-y-md rounded-lg border border-outline-variant bg-surface-container p-md">
        <div className="flex flex-col items-center space-y-sm py-lg">
          {found ? (
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/20 text-primary">
              <span className="material-symbols-outlined">check</span>
            </div>
          ) : (
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-primary/20 border-t-primary" />
          )}
          <p className={`font-code-md text-body-sm ${found ? "text-primary" : "animate-pulse text-on-surface-variant"}`}>
            {found ? "Engine running · v1.0.0" : "Provisioning local node…"}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-md border-l-2 border-primary bg-surface-container-low p-sm">
        <span className="material-symbols-outlined text-[20px] text-primary">terminal</span>
        <p className="font-code-md text-body-sm text-on-surface-variant">
          {found ? "Handshake complete on port 7432" : "Waiting for handshake on port 7432"}
        </p>
      </div>

      <button
        onClick={onNext}
        disabled={!found}
        className={`flex h-8 w-full items-center justify-center font-label-caps text-label-caps uppercase transition-opacity ${
          found ? "bg-primary text-on-primary hover:opacity-90" : "cursor-not-allowed bg-surface-container-highest text-outline opacity-50"
        }`}>
        Continue
      </button>
    </section>
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
    <section className="space-y-lg">
      <div className="space-y-base">
        <h2 className="font-headline-md text-headline-md">What are you working on?</h2>
        <p className="font-body-sm text-body-sm text-on-surface-variant">Configure your primary memory domain.</p>
      </div>

      <div className="space-y-md">
        <div>
          <label className="mb-base block font-label-caps text-label-caps uppercase text-on-surface-variant">Workspace Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Project 'Acheron'"
            type="text"
            className="w-full rounded-lg border border-outline-variant bg-surface-container px-md py-sm font-body-md text-body-md text-on-surface outline-none transition-all focus:border-primary"
          />
        </div>
        <div>
          <label className="mb-base block font-label-caps text-label-caps uppercase text-on-surface-variant">Primary Context</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onBlur={suggest}
            placeholder="e.g. Architecting a distributed vector database using Rust…"
            className="h-24 w-full resize-none rounded-lg border border-outline-variant bg-surface-container px-md py-sm font-body-md text-body-md text-on-surface outline-none transition-all focus:border-primary"
          />
        </div>
      </div>

      <button
        onClick={create}
        disabled={busy || !name.trim()}
        className="flex h-8 w-full items-center justify-center bg-primary font-label-caps text-label-caps uppercase text-on-primary transition-opacity hover:opacity-90 disabled:opacity-40">
        {busy ? "Creating…" : "Create Workspace"}
      </button>
    </section>
  )
}

function Ready({ name }: { name: string }) {
  return (
    <section className="space-y-lg">
      <div className="flex flex-col items-center space-y-md py-lg text-center">
        <div className="mb-md flex h-16 w-16 items-center justify-center rounded-full border border-primary bg-primary/10 text-primary">
          <span className="material-symbols-outlined text-[32px]">check_circle</span>
        </div>
        <div className="space-y-xs">
          <h2 className="font-headline-lg text-headline-lg text-on-surface">{name} ready</h2>
          <p className="font-body-md text-body-md text-on-surface-variant">Synchronization bridge established successfully.</p>
        </div>
      </div>

      <div className="rounded-lg border border-outline-variant bg-surface-container p-md">
        <p className="text-center font-body-sm text-body-sm italic text-on-surface-variant">
          "Your persistent state will now follow you through every LLM session."
        </p>
      </div>

      <div className="space-y-sm pt-md">
        <a href="https://claude.ai" target="_blank" rel="noreferrer" className="flex h-8 w-full items-center justify-center gap-sm bg-primary font-label-caps text-label-caps uppercase text-on-primary transition-opacity hover:opacity-90">
          Open Claude.ai <span className="material-symbols-outlined text-[16px]">open_in_new</span>
        </a>
        <button
          onClick={() => chrome.tabs.create({ url: chrome.runtime.getURL("tabs/dashboard.html") })}
          className="flex h-8 w-full items-center justify-center bg-transparent font-label-caps text-label-caps uppercase text-outline transition-colors hover:text-on-surface">
          View Dashboard
        </button>
      </div>
    </section>
  )
}

export default Onboarding
