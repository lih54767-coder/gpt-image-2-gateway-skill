# GPT Image 2 Gateway Skill

A portable [Agent Skill](https://agentskills.io/specification) with a local Python CLI for **one OpenAI-compatible gateway exposing `gpt-image-2`**. Each user configures their gateway URL and API key once; subsequent agent calls need neither value. No MCP server, hosted service, or multi-model registry is required.

The skill does **not** provide a gateway or an API key. It sends image requests only to the URL you configure and has no silent fallback to another image provider.

## Quick start

Requires Python 3.11+, a reachable compatible gateway, and an API key issued by that gateway.

```bash
git clone https://github.com/lih54767-coder/gpt-image-2-gateway-skill.git
cd gpt-image-2-gateway-skill
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/image_gen_gateway.py configure --base-url https://YOUR-GATEWAY.example/v1
.venv/bin/python scripts/image_gen_gateway.py status
.venv/bin/python scripts/image_gen_gateway.py generate --prompt 'A blue triangle on white paper' --out ./output/triangle.png
```

`configure` prompts privately for the gateway **API key**; do **not** paste it into chat or put it on the command line. For noninteractive deployment, inject it into a temporary environment variable using your secret manager and run `configure --base-url URL --key-env VARIABLE_NAME` (the CLI argument is the **name**, not the secret). On Windows 11, open PowerShell in the cloned directory and use:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\image_gen_gateway.py configure --base-url https://YOUR-GATEWAY.example/v1
.\.venv\Scripts\python.exe scripts\image_gen_gateway.py status
.\.venv\Scripts\python.exe scripts\image_gen_gateway.py generate --prompt "A blue triangle on white paper" --out .\output\triangle.png
```

The key is entered only during the first `configure` (or when changing it).

The CLI saves `config.json` (URL and optional Responses host model) and `key` (private API key) outside this repository: under `${XDG_CONFIG_HOME:-~/.config}/gpt-image-2-skill/` with mode `0600` on Unix, or `%LOCALAPPDATA%\gpt-image-2-skill\` with per-user inherited ACLs on Windows. `IMAGE2_CONFIG_DIR=/absolute/path` isolates agents sharing an OS account; `IMAGE2_API_KEY` overrides the saved key for an invocation. Do not confuse this gateway key with a public browser key or your agent's chat-model key.

To install as an agent skill, place this repository directory in your agent's skills path so it can discover `SKILL.md`. The agent must be able to execute local scripts and reach your configured gateway. Configure once on **the agent's machine**; credentials are not transferred by cloning the repository. See [SKILL.md](SKILL.md) for the agent workflow.

## Commands

Run these from the repository directory with `.venv/bin/python scripts/image_gen_gateway.py` in place of `image2`:

| Command | Purpose |
| --- | --- |
| `image2 configure --base-url https://YOUR-GATEWAY.example/v1` | Save URL and privately prompted key once; optional `--host-model` for Responses |
| `image2 status` | Show configured URL and whether a key is available; never print the key |
| `image2 generate --prompt '...' --out ./output/new.png` | Text-to-image via Images API |
| `image2 edit --image ./source.png --prompt '...' --out ./output/edited.png` | Edit an image; repeat `--image` for references, or use `--mask` |
| `image2 generate-batch --input ./jobs.jsonl --out-dir ./output/batch` | Generate from a JSONL job file |
| `image2 tool --prompt '...' --out ./output/tool.png` | Hosted image tool via Responses API, if your gateway supports it |

`tool` requires a **gateway-supported Responses host model**, distinct from the fixed image model `gpt-image-2`. Set one with `configure --host-model MODEL` or `tool --mainline-model MODEL`; the default `gpt-6-astra` is specific to the original deployment and may be unavailable elsewhere. Other supported options include streaming, partial previews, transparency, output formatting and downscaling. Run `image2 COMMAND --help` and read [the command reference](references/gateway-image2.md) for details. When continuing an edit, resend the previous output as `--image`; historical response IDs alone and File ID upload are **not** universally supported.

## Verification and limitations

```bash
.venv/bin/python -m unittest discover -s tests -q
```

These tests are offline: they verify CLI behavior and configuration without proving your gateway works. Make a small live image request and inspect the output after configuring **your** gateway. Both Images API and Responses API routes are separately dependent on gateway support. Some gateways return different dimensions or fewer previews than requested. The original deployment's results in the command reference are not guarantees for other deployments.

The project is not affiliated with or endorsed by OpenAI. Its use of model identifiers describes gateway compatibility, not a claim of model availability or entitlement. Never commit API keys, configuration files, generated private images, or downloaded inputs.

## Contributing & license

See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [Apache-2.0](LICENSE). Portions of the prompt/thumbnail helpers were adapted from the Apache-2.0-licensed OpenAI imagegen skill; see [NOTICE](NOTICE). OpenAI SDK and Pillow are runtime dependencies under their respective licenses.
