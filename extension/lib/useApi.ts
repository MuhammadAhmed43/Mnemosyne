import { useEffect, useState } from "react"

import { MnemosyneAPI } from "~lib/api"

/** Returns a probed API client once the engine is reachable, else null. */
export function useApi(): { api: MnemosyneAPI | null; online: boolean } {
  const [api, setApi] = useState<MnemosyneAPI | null>(null)
  const [online, setOnline] = useState(false)

  useEffect(() => {
    let cancelled = false
    chrome.storage.local.get("auth_token").then(({ auth_token }) => {
      const client = new MnemosyneAPI(auth_token ?? "")
      client.probe().then((health) => {
        if (cancelled) return
        setApi(client)
        setOnline(health !== null)
      })
    })
    return () => {
      cancelled = true
    }
  }, [])

  return { api, online }
}
