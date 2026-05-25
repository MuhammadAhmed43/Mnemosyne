// Per-platform DOM selectors + detection (Doc 03 §3.1, Plan 06).
// NOTE: these selectors are inherently brittle — AI platform UIs change often.
// They must be re-validated against the live sites on each release.

import type { Platform } from "~lib/types"

export interface PlatformConfig {
  platformName: Platform
  urlPattern: RegExp
  chatContainerSelector: string
  aiResponseSelector: string
  aiTextSelector: string
  userTextSelector: string
  inputSelector: string
  streamingIndicator: string
  injectionTarget: string
}

export const claudeConfig: PlatformConfig = {
  platformName: "claude",
  urlPattern: /claude\.ai/,
  chatContainerSelector: '[class*="conversation"], main',
  aiResponseSelector: '[data-testid="ai-message"], .font-claude-message, [class*="font-claude"]',
  aiTextSelector: ".prose, .markdown",
  userTextSelector: '[data-testid="user-message"], .whitespace-pre-wrap',
  inputSelector: 'div[contenteditable="true"], textarea',
  streamingIndicator: '.result-streaming, [class*="streaming"]',
  injectionTarget: "main",
}

export const chatgptConfig: PlatformConfig = {
  platformName: "chatgpt",
  urlPattern: /(chat\.openai\.com|chatgpt\.com)/,
  chatContainerSelector: 'main, [class*="react-scroll-to-bottom"]',
  aiResponseSelector: '[data-message-author-role="assistant"]',
  aiTextSelector: ".markdown, .prose",
  userTextSelector: '[data-message-author-role="user"] .whitespace-pre-wrap',
  inputSelector: "#prompt-textarea, textarea",
  streamingIndicator: ".result-streaming",
  injectionTarget: "main",
}

export const geminiConfig: PlatformConfig = {
  platformName: "gemini",
  urlPattern: /gemini\.google\.com/,
  chatContainerSelector: ".conversation-container, main",
  aiResponseSelector: ".model-response-text, [class*='response-container']",
  aiTextSelector: ".markdown-main-panel, .markdown",
  userTextSelector: ".query-text, .query-content",
  inputSelector: ".ql-editor, textarea",
  streamingIndicator: ".loading-indicator",
  injectionTarget: "main",
}

const PLATFORMS = [claudeConfig, chatgptConfig, geminiConfig]

export function detectPlatform(url: string): PlatformConfig | null {
  return PLATFORMS.find((p) => p.urlPattern.test(url)) ?? null
}
