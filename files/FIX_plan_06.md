# FIX — Plan 06: Chrome Extension — Manifest, Background & Content Scripts
## Fix for C-06
---

## HOW TO USE THIS FILE
One character change in one config file.

---

## FIX C-06 — Wrong success color in Tailwind config
**File to edit:** `extension/tailwind.config.js`

**Find:**

```js
        success: '#22C55E',
```

**Replace with:**

```js
        success: '#10B981',  // Tailwind emerald-500 — matches Doc 09 §2.1 design token --color-success
```

**Why:** Doc 09 §2.1 specifies `--color-success: #10B981` (Tailwind emerald-500).
The plan uses `#22C55E` (Tailwind green-500). These are visually distinct — green-500
is a brighter, more saturated green while emerald-500 is teal-leaning. All success states
across the extension (completed goals shown in the sidebar, confirmed extractions, approved
pending reviews) will render in the wrong color and be inconsistent with the dashboard
design system if this is not corrected.
(Ref: Doc 09 §2.1, C-06 conflict report)

---

## No other changes needed in Plan 06.
