// Lightweight, self-contained toast for in-page feedback (capture saved, note
// saved, errors). Rendered in its own shadow root so host-page CSS can't touch
// it. Stacks multiple toasts and auto-dismisses.

const TOAST_HOST_ID = "mnemosyne-toast-host"

function ensureHost(): ShadowRoot {
  let host = document.getElementById(TOAST_HOST_ID)
  if (host?.shadowRoot) return host.shadowRoot
  host = document.createElement("div")
  host.id = TOAST_HOST_ID
  const shadow = host.attachShadow({ mode: "open" })
  const style = document.createElement("style")
  style.textContent = `
    .wrap{position:fixed;bottom:18px;right:18px;z-index:2147483647;display:flex;
      flex-direction:column;gap:8px;align-items:flex-end;font-family:Inter,system-ui,sans-serif}
    .t{background:rgba(30,31,35,.72);-webkit-backdrop-filter:blur(20px) saturate(140%);
      backdrop-filter:blur(20px) saturate(140%);color:#e3e2e7;border:1px solid #464554;
      border-left:3px solid #c2c1ff;border-radius:4px;padding:9px 13px;font-size:13px;
      box-shadow:0 12px 30px rgba(0,0,0,.55);opacity:0;transform:translateY(8px);
      transition:opacity .18s,transform .18s;max-width:320px}
    .t.show{opacity:1;transform:translateY(0)}
    .t.err{border-left-color:#ffb4ab}
    .t .sub{color:#c7c4d6;font-size:11px;margin-top:2px}
  `
  shadow.appendChild(style)
  const wrap = document.createElement("div")
  wrap.className = "wrap"
  // Announce toasts to screen readers (e.g. "Saved 3 memories"). WCAG 4.1.3.
  wrap.setAttribute("role", "status")
  wrap.setAttribute("aria-live", "polite")
  shadow.appendChild(wrap)
  document.body.appendChild(host)
  return shadow
}

export function showToast(message: string, opts: { sub?: string; error?: boolean; ms?: number } = {}): void {
  try {
    const shadow = ensureHost()
    const wrap = shadow.querySelector(".wrap") as HTMLElement
    const el = document.createElement("div")
    el.className = `t${opts.error ? " err" : ""}`
    el.innerHTML = `<div>${escapeHtml(message)}</div>${opts.sub ? `<div class="sub">${escapeHtml(opts.sub)}</div>` : ""}`
    wrap.appendChild(el)
    requestAnimationFrame(() => el.classList.add("show"))
    const ms = opts.ms ?? 3200
    setTimeout(() => {
      el.classList.remove("show")
      setTimeout(() => el.remove(), 220)
    }, ms)
  } catch {
    /* never let UI feedback throw into the host page */
  }
}

function escapeHtml(s: string): string {
  const d = document.createElement("div")
  d.textContent = s
  return d.innerHTML
}
