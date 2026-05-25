// Client-side pre-filter mirroring the backend (Doc 13 §4.1). Defense in depth:
// the backend filters authoritatively, but this avoids even sending sensitive
// text over localhost.

const PATTERNS: RegExp[] = [
  /sk-ant-[A-Za-z0-9-]{20,}/,
  /sk-[A-Za-z0-9]{20,}/,
  /AKIA[A-Z0-9]{16}/,
  /AIza[0-9A-Za-z\-_]{35}/,
  /github_pat_[A-Za-z0-9_]{82}/,
  /ghp_[A-Za-z0-9]{36}/,
  /(?:api[_-]?key|secret|token|password|passwd|pwd)\s*[=:]\s*["']?[A-Za-z0-9\-_+/]{20,}/i,
  /Bearer\s+[A-Za-z0-9\-._~+/]+=*/,
  /-----BEGIN (?:RSA |EC )?PRIVATE KEY-----/,
  /\b\d{3}-\d{2}-\d{4}\b/,
  /\b\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}\b/,
  /(?:postgres(?:ql)?|mysql|mongodb|redis):\/\/[^:\s]+:[^@\s]+@/i,
]

export function containsSensitiveData(text: string): boolean {
  return PATTERNS.some((p) => p.test(text))
}
