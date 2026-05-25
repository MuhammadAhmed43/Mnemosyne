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
    .t{background:#111118;color:#F0F0F5;border:1px solid #2A2A3A;border-left:3px solid #7C3AED;
      border-radius:8px;padding:9px 13px;font-size:13px;box-shadow:0 6px 20px rgba(0,0,0,.45);
      opacity:0;transform:translateY(8px);transition:opacity .18s,transform .18s;max-width:320px}
    .t.show{opacity:1;transform:translateY(0)}
    .t.err{border-left-color:#EF4444}
    .t .sub{color:#8B8BA7;font-size:11px;margin-top:2px}
  `
  shadow.appendChild(style)
  const wrap = document.createElement("div")
  wrap.className = "wrap"
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
