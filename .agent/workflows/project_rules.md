---
description: Project-specific coding rules learned from PlexAither development mistakes
---

## Python & Windows Rules

### MIME Types on Windows + Flask + Waitress
**ALWAYS** use `@app.after_request` to enforce MIME types. Do NOT rely on `send_from_directory(mimetype=...)` or per-route `response.headers` — Waitress strips these on `304 Not Modified` responses silently.

```python
@app.after_request
def force_mimetypes(response):
    if request.path.endswith('.js'):
        response.content_type = 'application/javascript'
    elif request.path.endswith('.css'):
        response.content_type = 'text/css'
    return response
```

### Single-Instance Daemon Lock
Any Python script launched via `.bat` or `.vbs` MUST include a UDP socket lock to prevent duplicate instances competing over the same port:

```python
try:
    _lock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    _lock.bind(('127.0.0.1', 50050))  # use an arbitrary secondary port
except OSError:
    print("[!] Already running. Exiting.")
    sys.exit(0)
```

### Silent Headless Stdout
When running via `pythonw` (no console), `sys.stdout` is `None`. Patch before any prints:

```python
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')
```

### Flask SPA Route Order
The SPA catch-all in Flask MUST check in this exact order:
1. API prefix guard → 404
2. File physically exists on disk → serve file
3. Everything else → serve `index.html`

Never let catch-all routes come before API routes.

### Multi-Arg Functions → Dataclasses
Any function with 4+ related parameters must use a `@dataclass` instead of raw positional args. Prevents argument-order bugs and makes intent clear.

### Torrent Title Matching — Always Normalize
Never use direct string comparison for media titles. Always normalize both sides to a canonical word list, converting `(Season X)` → `S0X` and lowercasing before comparison:

```python
def normalize_title(title: str) -> List[str]:
    title = re.sub(r'\(?Season\s+(\d+)\)?', lambda m: f"S{int(m.group(1)):02d}", title, re.IGNORECASE)
    return [w.lower() for w in re.findall(r'\w+', title)]
```

---

## SvelteKit + Svelte 5 Rules

### `+layout.svelte` MUST Declare `children`
Any layout that uses `{@render children()}` MUST declare the `children` prop. Missing this causes a completely silent blank screen at runtime — no console error, no DOM output:

```svelte
<script lang="ts">
  import type { Snippet } from 'svelte';
  const { children }: { children: Snippet } = $props();
</script>
{@render children()}
```

### No Generic Annotations on Runes in `.svelte` Files
The `esrap` Svelte 5 AST compiler crashes on inline TypeScript generics:
- ❌ `$state<AppState>({...})`
- ❌ `let x: ReturnType<typeof setInterval>`
- ✅ `$state({...})` — plain, no generic
- ✅ `let x;` — untyped, complex types go in `.ts` files

### Build Output Must Not Be the Static Folder
Never point Flask's `static_folder` at the same directory Vite writes to. The running server holds the directory open, causing `EBUSY` on Windows during rebuild. Use separate names:
- Flask serves `frontend/dist/`
- Vite writes to `frontend/dist/` (but only after killing the server first)
- Add `frontend/dist/` and `frontend/.svelte-kit/` to `.gitignore`

### Always Rebuild After Frontend Source Changes
The workflow for any frontend change:
1. Kill the server (system tray → Quit)
2. `npm run build` in `frontend/`
3. Restart `run.bat`

---

## UI Animation Rules

### Use `requestAnimationFrame` Lerp for Data-Driven Bars, Not CSS Transitions
CSS `transition: width Xs` double-animates with polling/SSE data and causes jank. Use a rAF lerp loop instead:

```typescript
function animate() {
  displayed += (target - displayed) * 0.07; // ~1s to reach target at 60fps
  rafId = requestAnimationFrame(animate);
}
```
Remove `transition` from any element whose value is driven by rAF.

### Frequently-Updating Numbers Must Use Tabular-Nums + `min-width`
Prevent layout shift on number updates:
```scss
.live-number {
  font-variant-numeric: tabular-nums;
  min-width: 4ch;
}
```
Format with `Math.round()` — no decimals on live numbers.
