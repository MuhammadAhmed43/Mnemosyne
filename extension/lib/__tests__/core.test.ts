import { describe, expect, test } from "vitest"

import { detectPlatform } from "../platformDetector"
import { containsSensitiveData } from "../sensitiveFilter"

describe("detectPlatform", () => {
  test("detects each platform", () => {
    expect(detectPlatform("https://claude.ai/chat/abc")?.platformName).toBe("claude")
    expect(detectPlatform("https://chatgpt.com/c/123")?.platformName).toBe("chatgpt")
    expect(detectPlatform("https://chat.openai.com/c/123")?.platformName).toBe("chatgpt")
    expect(detectPlatform("https://gemini.google.com/app")?.platformName).toBe("gemini")
  })
  test("returns null for unsupported sites", () => {
    expect(detectPlatform("https://example.com")).toBeNull()
  })
})

describe("containsSensitiveData", () => {
  test("flags secrets", () => {
    expect(containsSensitiveData("key sk-abc123def456ghi789jkl012mno345pqr")).toBe(true)
    expect(containsSensitiveData("AKIAIOSFODNN7EXAMPLE")).toBe(true)
    expect(containsSensitiveData("ssn 123-45-6789")).toBe(true)
    expect(containsSensitiveData("postgresql://u:p@localhost/db")).toBe(true)
  })
  test("passes clean text", () => {
    expect(containsSensitiveData("We decided to use FastAPI for the backend")).toBe(false)
  })
})
