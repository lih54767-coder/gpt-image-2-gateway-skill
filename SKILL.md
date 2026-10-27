---
name: imagegen
description: Use when generating or editing bitmap images through a user-configured OpenAI-compatible gateway. On first setup it probes the gateway for gpt-image-2 / 2.5-flare / 2.5-sunburst and auto-selects per intent (Sunburst final, Flare drafts, Image 2 fallback). Includes a portable CLI for generation, edits, masks, references, batches and streaming. Do not use for other image models or code-native SVG/HTML assets.
version: 2.3.0
author: lih54767-coder
license: Apache-2.0
compatibility: Python 3.11+, access to a configured OpenAI-compatible image gateway (model availability varies by gateway); install requirements.txt.
---

# Gateway Image Generation (Image 2 / 2.5)

This is a **skill with bundled CLI code**, not an MCP service. It calls only the gateway URL configured by the local user and supports exactly `gpt-image-2`, `gpt-image-2.5-flare`, and `gpt-image-2.5-sunburst` on the Images API. `configure` probes the gateway's advertised models once and caches them; `--model auto` (the CLI default) picks by intent from that cache — Sunburst for final work, Flare for drafts, falling back to Image 2 only when the gateway advertises nothing newer. Explicit `--model` values are never silently substituted. Do not use a text-model Responses tool call as a substitute for an Images API request. It does not use the agent's chat-model credentials or silently try another provider. Each installation must complete its own private setup once. Never request a key in chat or print a key in tool output.

## Setup once, per user/agent environment

Install `requirements.txt` in an isolated Python environment (Python 3.11+). On Linux/macOS, from the installed skill directory (the directory containing `SKILL.md`), run:

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/image_gen_gateway.py configure --base-url https://YOUR-GATEWAY.example/v1
.venv/bin/python scripts/image_gen_gateway.py status
```

All later CLI calls likewise use `.venv/bin/python scripts/image_gen_gateway.py ...` from this directory (or another interpreter with `requirements.txt` installed). On Windows 11 PowerShell, replace the interpreter with `.\.venv\Scripts\python.exe` and run `py -3 -m venv .venv` for initial setup; the public repository README has complete copyable Windows commands. Do not package the local `.venv` with the skill.

`configure` privately prompts for the gateway **API key** on a terminal; the key is **not** a public browser key and is never included in a command argument. For unattended local setup, set a temporary environment variable yourself and use `configure --base-url URL --key-env VARIABLE_NAME` (the argument is the **variable name**, not its value). Do not send the value through an agent chat. `configure` also **probes the gateway's `/v1/models`** for the supported image models and stores the detected list; if the probe fails, nothing is written and the error is reported. `--host-model MODEL` optionally configures a gateway-supported Responses API host model for the separate `tool` command; it does not select the Images API model.

Config is stored **outside the distributable skill** in `${XDG_CONFIG_HOME:-~/.config}/gpt-image-2-skill/` on Unix (mode `0600`), or `%LOCALAPPDATA%\gpt-image-2-skill\` on Windows (per-user inherited ACLs): `config.json` for URL/optional host model and `key` for the private gateway API key. `IMAGE2_API_KEY` can override the saved key at invocation time. `IMAGE2_CONFIG_DIR=/absolute/path` isolates installations for agents sharing an OS account. No global URL, Key or `/root` path is bundled. Use `status` to verify URL and key availability without exposing the key. If setup is missing, stop with a setup instruction; never fall back to OpenAI directly.

The agent needs terminal or equivalent local script execution and access to its configured gateway. A remote agent with no access to this filesystem cannot execute the skill as-is; that is when a separate remote tool service would be needed.

## Model selection (agent policy)

1. If the user names a model, use it exactly. Never silently replace an unavailable model or retry on another provider.
2. Otherwise rely on the CLI's detection: `configure` (and the first `--model auto` call on an older config) probes the gateway's advertised models and caches them in the private config. With 2.5 available, `auto` resolves to **Sunburst for final/polished work and precise edits, Flare for quick drafts and batch composition**. For an individual draft, set `--quality low` or explicitly `--model gpt-image-2.5-flare`; bare `generate` and `edit` default to Sunburst. Unspecified `generate-batch` jobs default to Flare, while a global/row explicit `--model` wins. If the gateway advertises only Image 2, `auto` uses Image 2 for everything — no fallback to other providers. `/v1/models` is an advertised-model check, **not proof** of each Images/Responses feature; verify real output on each new gateway.
3. Re-run `configure` (or any command with `--model auto` after clearing the cached `available_models`) when the gateway's model lineup changes; the cache is not refreshed automatically on a schedule.
4. For `generate-batch`, pass `--model` for the overall batch and optionally set `"model"` on individual JSONL rows. Record/report the selected model per delivery. Gateway capability is per route: an Images API success does not prove the optional Responses `tool` route works.

## Workflow

1. If setup is absent, ask the user to run `configure` privately on the agent's machine (or use their permitted local secret setup); do not collect credentials in chat. Verify with `status`.
2. New image: `generate --model auto --prompt ... --out /path/image.png`. Existing image: `edit --model auto --image /path/source.png --prompt ... --out /path/edited.png`. `auto` prefers Sunburst for single final images/edits if the user's gateway advertises it; for quick drafts add `--quality low` (or explicitly request Flare if the gateway has it). If the user names a specific model, pass exactly that `--model` instead. Add another `--image /path/reference.png` for visual reference; `--mask /path/mask.png` is an alpha PNG of exactly the source image's **actual** dimensions.
3. For multiple prompts, use `generate-batch --model auto --input /path/jobs.jsonl --out-dir /path/results`: unspecified jobs prefer Flare where available. `--n` runs separate single-image calls on gateways that return fewer images for one multi-output call. Image 2.5 also supports `--quality xhigh|max`; use `high` unless extra quality is specifically wanted.
4. For Responses hosted image tool on gateways that support it, use `tool --model auto --prompt ... --out /path/image.png` or `tool --model auto --image /path/last-output.png --prompt ... --action edit --out /path/next.png`; choose/configure a compatible host model. Images API (`generate`, `edit`) and Responses `tool` are separate routes: **prefer direct Images API** and do not assume one route's support proves the other.
5. Inspect each final image and verify file format/dimensions. Do not overwrite existing files without explicit permission (`--force`); report gateway errors without exposing request bodies or credentials.

Gateway-specific command details and the **original site's** capability limits: [references/gateway-image2.md](references/gateway-image2.md). Those test results do not establish what another user's gateway supports. For Feishu delivery on Hermes, see [references/feishu-image-delivery.md](references/feishu-image-delivery.md).

## Common pitfalls

- Reusing the agent's chat `OPENAI_API_KEY` silently can send the wrong credential to the configured URL. This CLI accepts only its private saved key or explicit `IMAGE2_API_KEY`. The historical `IMAGE2_*` environment variables and `gpt-image-2-skill` config directory are kept to preserve installed configurations; they do **not** restrict `--model` to Image 2.
- A response ID alone may not restore a previous image across gateways. Resend the last saved image as `--image` for reliable edits. File ID requires gateway file-upload support; do not claim it works without an end-to-end test.
- Stream previews are optional even if requested. Inspect actual preview files/events and the final file before claiming success.
- The original upstream `scripts/image_gen.py` is **not** used by this portable gateway CLI. The portable bundle contains the CLI entrypoint, gateway core, and self-contained prompt/downscale helper.

## Verification

Run `python3 -m unittest discover -s tests -q` in the installed skill directory **with an empty `XDG_CONFIG_HOME` or `IMAGE2_CONFIG_DIR`** to prevent hidden dependence on the maintainer's private config. Then make one low-quality live image using **each new 2.5 model** on the user's configured gateway and inspect format/dimensions before declaring that gateway supported. On the original site, separate direct Images tests passed for 2.5 generation, edit, masks + second reference, alpha PNG/WebP, `xhigh`/`max`, streaming final, batch, and Sunburst Responses tool generation/edit. These are **site-specific**: a model listed by `/v1/models` does not guarantee either route or every parameter is accepted by another gateway. Partial streaming previews may be absent, and output dimensions may differ from requested size. Never include local configuration/key files in the shared skill archive.
