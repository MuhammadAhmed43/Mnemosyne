# FIX — Plan 07: Extension Sidebar UI
## Fix for C-07
---

## HOW TO USE THIS FILE
Update the header comment and any width declarations. Details below.

---

## FIX C-07 — Sidebar width 360px → 380px
**Files to edit:** `extension/sidebar/index.tsx` and `extension/content/injector.ts`

### Change 1 — Plan 07 section header (documentation, line 7)

**Find:**
```
## 1. SIDEBAR (Injected as side panel, 360px wide)
```
**Replace with:**
```
## 1. SIDEBAR (Injected as side panel, 380px wide)
```

### Change 2 — `extension/sidebar/index.tsx`

Search the file for any of the following patterns and update from 360 to 380:

```tsx
// Find any of these forms:
width: '360px'
width: "360px"
w-[360px]
minWidth: 360
maxWidth: 360
style={{ width: 360 }}
```

**Replace all occurrences with the 380px equivalent:**
```tsx
width: '380px'
width: "380px"
w-[380px]
minWidth: 380
maxWidth: 380
style={{ width: 380 }}
```

### Change 3 — `extension/content/injector.ts`

The injector creates the sidebar iframe and sets its width. Find:

```ts
// Any of these patterns:
iframe.style.width = '360px'
width: '360px'
SIDEBAR_WIDTH = 360
const SIDEBAR_WIDTH = '360px'
```

**Replace with:**
```ts
iframe.style.width = '380px'
width: '380px'
SIDEBAR_WIDTH = 380
const SIDEBAR_WIDTH = '380px'   // Doc 09 §9: default sidebar width
```

**Why:** Doc 09 §9 specifies "Default: 380px" for the sidebar width. The plan header and any
generated width values say 360px. The sidebar components are designed for 380px — layout
at 360px causes unwanted horizontal overflow in the Memory Browser and Graph View components.
This also affects the page-body margin-right offset that the injector applies to prevent
content from being hidden behind the sidebar: that offset must also be 380px.
(Ref: Doc 09 §9, C-07 conflict report)

---

## No other changes needed in Plan 07.
