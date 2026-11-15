# Nosana GPU Deployment — Ollama / GLM-4.7-Flash

Status: **Working and verified** as of 2026-11-15 16:51 UTC.

## Final, verified connection info (for the Daytona-sandbox teammate)

```
NOSANA_BASE_URL=https://51mkeksqRq6mKmTwAnVpTwRBuGQjodpizYakEvwd9L64.node.k8s.prd.nos.ci
NOSANA_MODEL_ID=glm-4.7-flash:q4_K_M
NOSANA_API_TYPE=openai-compatible
NOSANA_CHAT_ENDPOINT=/v1/chat/completions
```

No API key is required.

Example full chat endpoint: `${NOSANA_BASE_URL}${NOSANA_CHAT_ENDPOINT}`
→ `https://51mkeksqRq6mKmTwAnVpTwRBuGQjodpizYakEvwd9L64.node.k8s.prd.nos.ci/v1/chat/completions`

Verified directly (not just via health check):
- `GET /api/tags` → model is actually registered: `glm-4.7-flash:q4_K_M`, capabilities `["completion","tools","thinking"]`
- `POST /v1/chat/completions` → returns a normal OpenAI-style chat completion
- `POST /v1/chat/completions` with `tools` → model correctly returns `tool_calls` (`finish_reason: "tool_calls"`)

Deployment: `flexible_testing_pancake (copy) (copy)`
Job ID: `J2QRQ5rcTSMkeaAbX6fP799oRCypHRScESkids9r4dfh`
GPU: RTX 3090, 24GB VRAM

## Root cause of the original bug (`/api/tags` → `{"models":[]}` with HTTP 200)

The original job definition used Nosana's `resources` block to pre-load the
model into the container via a `target` mount path (e.g. `/models` or
`/root/.ollama/models`). **Nosana `resources` mounts are read-only.** Ollama
needs to *write* manifest files into its model directory on every startup
(even if the blobs are already present), so any `target` mount there causes
Ollama to fail silently (empty model list) or crash with:

```
error="mkdir /root/.ollama/models/manifests-v2: read-only file system: ensure path elements are traversable"
```

Critically, the deployment's `health_checks` only checks the HTTP **status
code** of `/api/tags` (expects 200), not the response body — so a totally
broken deployment with zero models still shows "healthy" in the dashboard.
**Always verify the response body, not just the health check status.**

## The fix

Drop the `resources` mechanism entirely. Instead, let Ollama manage its own
(writable, ephemeral) model storage by pulling the model itself at
container startup, via `cmd`:

```sh
ollama serve & sleep 5 && ollama pull $MODEL && wait
```

See `job.json` for the full, working job definition. This matches Nosana's
own documented pattern for Ollama deployments (see
`learn.nosana.com/inference/examples/ollama.html`).

Trade-off: the ~17.7GB model is re-downloaded on every fresh deployment
(Nosana's resource cache does not apply here since this doesn't use
`resources`, and in any case that cache is per-GPU-node). Startup takes a
few minutes before the model is queryable.

## Files in this folder

- `job.json` — the final, verified-working Nosana job definition.
- `.env.example` — the connection variables above, in `.env` format.
- `test_inference.py` — verifies model registration, chat completions, and
  tool calling against a live endpoint. Run it from an environment with
  normal internet access (e.g. the Daytona sandbox), not from a locked-down
  sandbox:
  ```
  pip install requests python-dotenv
  cp .env.example .env   # edit if needed
  python test_inference.py
  ```

## Known dashboard bug

The "Create Revision" action in the Nosana dashboard's deployment Actions
menu does not work (no visible effect — no modal, no new log entry, no
network request). Workaround used throughout this fix: **Duplicate →
Configure → Edit as JSON → Save changes → Deploy now**. Note this creates a
genuinely new deployment (new ID, new billing), not a revision of the
existing one — the old deployment must be stopped manually to avoid being
billed for both.

## Cleanup / cost tracking

Three earlier failed deployment attempts exist in the account, all
**stopped** (not billing):
- `FJKF1JJsEg2HqvV3BRTdQpbYXWfyzKeQ1AG8ZRzqy9sm` (original, pre-fix)
- `BD3YsTZeVdphksBBC8mazSWxSjL9NkZJLdDv9n1tfUJG` (fix attempt #1 — removed `target`, still broken)
- `C6VZCBb4CpiHiGsRgpNNsmEBrZYQsMC4vwJX5aSPtrL1` (fix attempt #2 — `target=/root/.ollama/models`, HTTP 500)

Only the working deployment (`J2QRQ5...`) is currently running and billing
(~$0.19/hr). Account balance at last check: **$8.78 in credits**.

**Reminder: stop the `J2QRQ5...` deployment once the hackathon is over** to
avoid ongoing GPU charges.
