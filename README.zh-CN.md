# GPT Image 2 中转站 Skill

[简体中文](README.zh-CN.md) | [English](README.md)

这是一个可移植的 [Agent Skill](https://agentskills.io/specification)，内置 Python CLI，专门调用**单个兼容 OpenAI 接口、提供 `gpt-image-2` 的中转站**。每位使用者在自己的机器上配置一次中转站 URL 和 API Key，之后 Agent 调用时无需反复填写。不需要 MCP 服务、托管服务或多模型注册系统。

本项目**不提供**中转站或 API Key。程序只向你配置的地址发送生图请求，不会在失败时悄悄切到其他生图服务。

## 快速开始

需要 Python 3.11+、可连接的兼容中转站，以及该中转站签发的 API Key。

Linux/macOS：

```bash
git clone https://github.com/lih54767-coder/gpt-image-2-gateway-skill.git
cd gpt-image-2-gateway-skill
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/image_gen_gateway.py configure --base-url https://YOUR-GATEWAY.example/v1
.venv/bin/python scripts/image_gen_gateway.py status
.venv/bin/python scripts/image_gen_gateway.py generate --prompt '白纸上的蓝色三角形' --out ./output/triangle.png
```

Windows 11：在 PowerShell 中运行：

```powershell
git clone https://github.com/lih54767-coder/gpt-image-2-gateway-skill.git
cd gpt-image-2-gateway-skill
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\image_gen_gateway.py configure --base-url https://YOUR-GATEWAY.example/v1
.\.venv\Scripts\python.exe scripts\image_gen_gateway.py status
.\.venv\Scripts\python.exe scripts\image_gen_gateway.py generate --prompt "白纸上的蓝色三角形" --out .\output\triangle.png
```

把 `https://YOUR-GATEWAY.example/v1` 换成你自己的中转站 API 地址。`configure` 会在终端中私密提示输入**中转站 API Key**；它不是可公开的浏览器 Key，**不要**贴进聊天、命令参数或仓库。后续无需重复配置；要更换 Key 时再运行 `configure`。无人值守部署时，可先通过可信的本地密钥管理方式设置临时环境变量，再用 `configure --base-url URL --key-env 变量名`；命令参数只写**变量名**，不写 Key 的值。

CLI 将 `config.json`（URL 和可选的 Responses 宿主模型）及 `key`（私有 API Key）存在仓库**以外**：Linux/macOS 默认为 `${XDG_CONFIG_HOME:-~/.config}/gpt-image-2-skill/`，文件权限为 `0600`；Windows 默认为 `%LOCALAPPDATA%\gpt-image-2-skill\`，继承当前用户目录的 ACL。多个 Agent 共用同一个系统账号时，可通过 `IMAGE2_CONFIG_DIR` 指定各自的绝对路径；`IMAGE2_API_KEY` 可在单次调用时覆盖已保存的 Key。不要把这个 Key 与 Agent 聊天模型的 Key 混用。

如需作为 Agent Skill 安装，把仓库目录放到 Agent 能发现 `SKILL.md` 的 skills 路径中。Agent 必须能在本机执行脚本并访问你配置的中转站；克隆仓库不会转移本地凭据。Agent 的操作流程见 [SKILL.md](SKILL.md)。

## 命令

下表中的 `image2` 是简写：在仓库目录下，Linux/macOS 用 `.venv/bin/python scripts/image_gen_gateway.py` 替换；Windows PowerShell 用 `.\.venv\Scripts\python.exe scripts\image_gen_gateway.py` 替换。

| 命令 | 用途 |
| --- | --- |
| `image2 configure --base-url https://YOUR-GATEWAY.example/v1` | 首次保存 URL，并在终端私密输入 Key；可用 `--host-model` 设置 Responses 宿主模型 |
| `image2 status` | 查看已配置的 URL 及是否有 Key，不输出 Key |
| `image2 generate --prompt '...' --out ./output/new.png` | 通过 Images API 文生图 |
| `image2 edit --image ./source.png --prompt '...' --out ./output/edited.png` | 编辑本地图片；可重复传入 `--image` 加参考图，或使用 `--mask` |
| `image2 generate-batch --input ./jobs.jsonl --out-dir ./output/batch` | 按 JSONL 任务文件批量生成 |
| `image2 tool --prompt '...' --out ./output/tool.png` | 经 Responses API 使用托管生图工具；取决于中转站是否支持 |

`tool` 需要中转站支持的 **Responses 宿主模型**，它与固定使用的图片模型 `gpt-image-2` 不同。可通过 `configure --host-model MODEL` 或 `tool --mainline-model MODEL` 设置；默认的 `gpt-6-astra` 来自最初部署的环境，其他中转站未必提供。CLI 还支持流式输出、局部预览、透明背景、格式转换与缩图；详情运行 `image2 子命令 --help` 并查看[命令参考](references/gateway-image2.md)。续改图片时，建议把上次生成的文件重新作为 `--image` 传入；**仅凭历史 Response ID** 和 **File ID 上传** 并非在所有中转站都可用。

## 验证与限制

Linux/macOS：

```bash
.venv/bin/python -m unittest discover -s tests -q
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

这些是**离线测试**，只验证 CLI 与配置逻辑，不能证明你的中转站实际支持生图。首次配置后，请在自己的中转站生成一张小图并检查文件。Images API 与 Responses API 是两条不同链路，必须分别以实际结果判断；不同中转站可能返回与请求不同的尺寸或更少的预览图。命令参考中原始部署的验收结果，不保证适用于其他中转站。仓库 CI 已在 Windows 与 Ubuntu 的 Python 3.11/3.12 上运行离线测试；尚未在 Win11 实机做中转站生图验收。

本项目与 OpenAI 没有关联，也未获其背书。文中模型名仅用于说明中转站兼容性，不表示模型一定可用或你拥有使用资格。不要向仓库提交 API Key、本机配置、私有生成图片或下载的输入图片。

## 贡献与许可

贡献指南见 [CONTRIBUTING.md](CONTRIBUTING.md)。项目采用 [Apache-2.0 许可证](LICENSE)。部分提示词与缩略图辅助代码改编自同为 Apache-2.0 许可的 OpenAI imagegen skill，归属与修改说明见 [NOTICE](NOTICE)。OpenAI SDK 和 Pillow 是运行依赖，各自遵循其许可证。
