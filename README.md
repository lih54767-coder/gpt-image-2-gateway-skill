# GPT Image Gateway Skill (Image 2 / 2.5)

[English](README.md) | [简体中文](README.zh-CN.md)

A portable [Agent Skill](https://agentskills.io/specification) with a local Python CLI for **one user-configured OpenAI-compatible image gateway**. Supports `gpt-image-2`, `gpt-image-2.5-flare` and `gpt-image-2.5-sunburst`. Each agent/user configures their own gateway URL and private API key once. No MCP server, hosted service, included gateway, or included API key. Never silently switches providers.

## Install and configure

Requires Python 3.11+, a reachable compatible gateway, and its own API key.

```bash
git clone https://github.com/lih54767-coder/gpt-image-2-gateway-skill.git
cd gpt-image-2-gateway-skill
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/image_gen_gateway.py configure --base-url https://YOUR-GATEWAY.example/v1
.venv/bin/python scripts/image_gen_gateway.py status
.venv/bin/python scripts/image_gen_gateway.py generate --prompt 'A blue triangle' --out ./output/triangle.png
```

`configure` privately prompts for the **gateway API key** in the terminal. Do not paste it into chat, command arguments, or the repository. For local unattended setup, inject a temporary environment variable through your secret manager and pass only its **name** with `--key-env VARIABLE_NAME`. The CLI checks the configured gateway's `/v1/models` using that key and caches the image models it advertises. An authentication/network error stops setup without recording a false Image 2 fallback. **A model listing is not proof every Images/Responses feature works:** test the endpoint on your gateway.

The private `config.json` (URL, cached model IDs, optional Responses host model) and `key` live **outside this repository**: `${XDG_CONFIG_HOME:-~/.config}/gpt-image-2-skill/` on Unix (files mode `0600`), or `%LOCALAPPDATA%\gpt-image-2-skill\` on Windows (per-user ACL). `IMAGE2_CONFIG_DIR` isolates agents sharing one OS user. `IMAGE2_API_KEY` can override the saved key for one invocation; reconfigure to refresh the model cache if gateway access changes. Never confuse this key with the agent's chat-model key or a public browser key.

On Windows 11 PowerShell, replace `.venv/bin/python` with `.\.venv\Scripts\python.exe`, create the environment with `py -3 -m venv .venv`, and use `scripts\image_gen_gateway.py`.

## Choosing a model

The Images API `generate`, `edit`, and `generate-batch` commands default to `--model auto`:

- For a **single polished image or precise edit**, `auto` prefers **Sunburst**.
- For a **quick draft**, add `--quality low` or explicitly request **Flare**. Unspecified batch jobs prefer **Flare** even when quality is `auto`.
- If the gateway advertises **only Image 2**, `auto` uses `gpt-image-2`. When only one 2.5 variant is available, `auto` uses that variant. Explicit `--model` always wins and is **never silently replaced**.

```bash
.venv/bin/python scripts/image_gen_gateway.py generate --prompt 'A tiny leaf' --quality low --out ./output/draft.png
.venv/bin/python scripts/image_gen_gateway.py generate --model gpt-image-2.5-sunburst --quality xhigh --prompt 'Detailed watercolor leaf' --out ./output/final.png
.venv/bin/python scripts/image_gen_gateway.py edit --image ./source.png --image ./reference.png --mask ./mask.png --prompt 'Change the leaf color' --out ./output/edit.png
.venv/bin/python scripts/image_gen_gateway.py generate-batch --input ./jobs.jsonl --out-dir ./output/batch
.venv/bin/python scripts/image_gen_gateway.py tool --mainline-model YOUR_SUPPORTED_TEXT_MODEL --image ./source.png --action edit --prompt 'Recolor it' --out ./output/tool-edit.png
```

`--mask` must be an alpha PNG with the **actual dimensions of the first input image**; transparent areas guide the edit, not a guaranteed pixel-perfect boundary. Repeat `--image` for references. `--n` is implemented as separate single-image requests to support gateways returning fewer images than requested. Image 2.5 adds `--quality xhigh|max`. Also supported: PNG/JPEG/WebP output, transparency, custom sizes, compression, streaming (partial previews optional), and local downscaling. See [command reference](references/gateway-image2.md) and [SKILL.md](SKILL.md).

`tool` is the separate Responses API image-generation-tool route: the **top-level host text model** is distinct from the **image tool model**. It is optional and requires gateway support. Image generation/editing should normally use the direct Images API. Re-send the last image via `--image` for reliable continued edits; historical Response IDs or File IDs alone are not universally supported.

## Verification and limits

Install this directory as a skill in an agent able to execute local scripts and access its configured gateway; cloning never transfers credentials. Offline tests (also run on Ubuntu and Windows in CI):

```bash
XDG_CONFIG_HOME=/tmp/image-skill-clean-test .venv/bin/python -m unittest discover -s tests -q
```

On Windows PowerShell, run `.\.venv\Scripts\python.exe -m unittest discover -s tests -q` with a fresh local config directory. Offline tests do **not** validate a third-party gateway. The original gateway has separately produced images with both 2.5 variants through generate/edit, masks + references, transparent output, `xhigh/max`, batch and streaming final; Sunburst's Responses tool generated and edited images. Other gateways and combinations must be checked independently. Requested dimensions can differ from returned dimensions, WebP may be a verified **local conversion** from PNG, and partial streaming previews may be absent. The original gateway's File ID upload and response-ID-only continuation have not been established; Flare's Responses-tool route has not been independently tested there. No C2PA upstream-model string audit is claimed.

No affiliation with or endorsement by OpenAI. Model names identify gateway compatibility, not guaranteed availability. Never commit API keys, user configs, input images, or private outputs.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md). [Apache-2.0](LICENSE). Portions of the prompt/downscale helpers derive from the Apache-2.0-licensed OpenAI imagegen skill; see [NOTICE](NOTICE). OpenAI SDK and Pillow are separately licensed dependencies.
