---
name: imagegen
description: Use when generating or editing bitmap images through a user-configured OpenAI-compatible gateway's gpt-image-2. Includes a portable CLI for prompt generation, local-image edits, masks, references, batches and streaming; requires one-time local gateway setup. Do not use for other image models or code-native SVG/HTML assets.
version: 2.0.0
author: lih54767-coder
license: Apache-2.0
compatibility: Python 3.11+, access to a gpt-image-2-compatible gateway; install requirements.txt.
---

# Gateway GPT Image 2

This is a **skill with bundled CLI code**, not an MCP service. It calls only the gateway URL configured by the local user, and pins the image model to `gpt-image-2`. It does not use the agent's chat-model credentials or silently try another provider. Each installation must complete its own private setup once. Never request a key in chat or print a key in tool output.

## Setup once, per user/agent environment

Install `requirements.txt` in an isolated Python environment (Python 3.11+). On Linux/macOS, from the installed skill directory (the directory containing `SKILL.md`), run:

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/image_gen_gateway.py configure --base-url https://YOUR-GATEWAY.example/v1
.venv/bin/python scripts/image_gen_gateway.py status
```

All later CLI calls likewise use `.venv/bin/python scripts/image_gen_gateway.py ...` from this directory (or another interpreter with `requirements.txt` installed). On Windows, use the corresponding `.venv/Scripts/python.exe` path. Do not package the local `.venv` with the skill.

`configure` privately prompts for the gateway **API key** on a terminal; the key is **not** a public browser key and is never included in a command argument. For unattended local setup, set a temporary environment variable yourself and use `configure --base-url URL --key-env VARIABLE_NAME` (the argument is the **variable name**, not its value). Do not send the value through an agent chat. `--host-model MODEL` optionally configures a gateway-supported Responses API host model; this does not change `gpt-image-2`.

Config is stored **outside the distributable skill** in `${XDG_CONFIG_HOME:-~/.config}/gpt-image-2-skill/`: `config.json` for URL/optional host model and `key` for the private gateway API key, both mode `0600`. `IMAGE2_API_KEY` can override the saved key at invocation time. `IMAGE2_CONFIG_DIR=/absolute/path` isolates installations for agents sharing an OS account. No global URL, Key or `/root` path is bundled. Use `status` to verify URL and key availability without exposing the key. If setup is missing, stop with a setup instruction; never fall back to OpenAI directly.

The agent needs terminal or equivalent local script execution and access to its configured gateway. A remote agent with no access to this filesystem cannot execute the skill as-is; that is when a separate remote tool service would be needed.

## Workflow

1. If setup is absent, ask the user to run `configure` privately on the agent's machine (or use their permitted local secret setup); do not collect credentials in chat. Verify with `status`.
2. New image: `generate --prompt ... --out /path/image.png`. Existing image: `edit --image /path/source.png --prompt ... --out /path/edited.png`. Add another `--image /path/reference.png` for visual reference; `--mask /path/mask.png` is an alpha PNG of exactly the source image's **actual** dimensions.
3. For multiple prompts, use `generate-batch --input /path/jobs.jsonl --out-dir /path/results`. `--n` runs separate single-image calls on gateways that return fewer images for one multi-output call.
4. For Responses hosted image tool on gateways that support it, use `tool --prompt ... --out /path/image.png` or `tool --image /path/last-output.png --prompt ... --action edit --out /path/next.png`; choose/configure a compatible host model. Images API (`generate`, `edit`) and Responses `tool` are separate routes: do not assume one route's support proves the other.
5. Inspect each final image and verify file format/dimensions. Do not overwrite existing files without explicit permission (`--force`); report gateway errors without exposing request bodies or credentials.

Gateway-specific command details and the **original site's** capability limits: [references/gateway-image2.md](references/gateway-image2.md). Those test results do not establish what another user's gateway supports. For Feishu delivery on Hermes, see [references/feishu-image-delivery.md](references/feishu-image-delivery.md).

## Common pitfalls

- Reusing the agent's chat `OPENAI_API_KEY` silently can send the wrong credential to the configured URL. This CLI accepts only its private saved key or explicit `IMAGE2_API_KEY`; the image model remains `gpt-image-2`.
- A response ID alone may not restore a previous image across gateways. Resend the last saved image as `--image` for reliable edits. File ID requires gateway file-upload support; do not claim it works without an end-to-end test.
- Stream previews are optional even if requested. Inspect actual preview files/events and the final file before claiming success.
- The original upstream `scripts/image_gen.py` is **not** used by this portable gateway CLI. The portable bundle contains the CLI entrypoint, gateway core, and self-contained prompt/downscale helper.

## Verification

Run `python3 -m unittest discover -s tests -q` in the installed skill directory (tests included in the distributable bundle). Then make one low-quality live image on the user's configured gateway and inspect the output before declaring that gateway supported. Never include local configuration/key files in the shared skill archive.
