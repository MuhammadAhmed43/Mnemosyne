import { useEffect, useState } from "react"

import { MnemosyneAPI } from "~lib/api"

/** Returns a probed API client. `checking` is true until the first probe
 *  resolves, so callers can show "Connecting…" instead of a false "offline"
 *  flash. The last-known status is cached to display instantly on reopen. */
export function useApi(): { api: MnemosyneAPI | null; online: boolean; checking: boolean } {
  const [api, setApi] = useState<MnemosyneAPI | null>(null)
  const [online, setOnline] = useState(false)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    let cancelled = false
    chrome.storage.local.get(["auth_token", "mn_last_online"]).then(({ auth_token, mn_last_online }) => {
      // Optimistically reflect the last-known state so the UI doesn't flash offline.
      if (!cancelled && mn_last_online) setOnline(true)
      const client = new MnemosyneAPI(auth_token ?? "")
      client.probe().then((health) => {
        if (cancelled) return
        const ok = health !== null
        setApi(client)
        setOnline(ok)
        setChecking(false)
        void chrome.storage.local.set({ mn_last_online: ok })
      })
    })
    return () => {
      cancelled = true
    }
  }, [])

  return { api, online, checking }
}
