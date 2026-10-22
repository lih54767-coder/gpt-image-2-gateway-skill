#!/usr/bin/env python3
"""Gateway-only GPT Image 2 CLI. Never logs credentials, image bytes or API bodies."""
from __future__ import annotations

import argparse
import base64
import binascii
import getpass
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
from urllib.parse import urlsplit

from PIL import Image, UnidentifiedImageError
from gateway_prompt import _augment_prompt, _derive_downscale_path, _downscale_image_bytes

MODEL = 'gpt-image-2'
SIZES = {'1024x1024', '1536x1024', '1024x1536'}
FORMATS = {'png': 'PNG', 'jpeg': 'JPEG', 'webp': 'WEBP'}
EXTENSIONS = {'png': {'.png'}, 'jpeg': {'.jpg', '.jpeg'}, 'webp': {'.webp'}}


def validate_size(value: str) -> str:
    if value == 'auto':
        return value
    match = re.fullmatch(r'(\d+)x(\d+)', value)
    if not match:
        raise ValueError('size must be WIDTHxHEIGHT or auto')
    w, h = map(int, match.groups())
    if not (w % 16 == h % 16 == 0 and max(w, h) <= 3840 and
            max(w, h) <= 3 * min(w, h) and 655360 <= w * h <= 8294400):
        raise ValueError('Image 2 size: edges multiple of 16, <=3840, aspect <=3:1, 655360..8294400 pixels')
    return value


def validate_output(background: str | None, output_format: str, compression: int | None) -> str:
    fmt = 'jpeg' if output_format == 'jpg' else output_format
    if fmt not in FORMATS:
        raise ValueError('output format must be png, jpeg or webp')
    if background not in (None, 'auto', 'opaque', 'transparent'):
        raise ValueError('background must be auto, opaque or transparent')
    if background == 'transparent' and fmt == 'jpeg':
        raise ValueError('transparent output requires png or webp')
    if compression is not None and (fmt == 'png' or not 0 <= compression <= 100):
        raise ValueError('output-compression requires jpeg/webp and 0..100')
    return fmt


def validate_images(paths: list[Path], mask: Path | None = None) -> None:
    if not 1 <= len(paths) <= 16:
        raise ValueError('edit requires 1..16 local images')
    for path in paths:
        if not path.is_file() or path.stat().st_size > 50 * 1024 * 1024:
            raise ValueError(f'invalid image path/size: {path}')
        try:
            with Image.open(path) as im:
                if im.format not in ('PNG', 'JPEG', 'WEBP'):
                    raise ValueError('input images must be PNG/JPEG/WEBP')
                im.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError(f'input is not an image: {path}') from exc
    if mask is not None:
        if not mask.is_file():
            raise ValueError(f'mask not found: {mask}')
        with Image.open(paths[0]) as source, Image.open(mask) as m:
            if m.format != 'PNG' or 'A' not in m.getbands() or m.size != source.size:
                raise ValueError('mask must be alpha PNG with same dimensions as first image')
            m.verify()


def _decode_image(value: str, fmt: str, compression: int | None = None) -> bytes:
    if not value:
        raise ValueError('empty image result')
    try:
        data = base64.b64decode(value, validate=True)
        with Image.open(BytesIO(data)) as im:
            im.load()
            if im.format != FORMATS[fmt]:
                print(f'Notice: gateway returned {im.format}, converting locally to {FORMATS[fmt]}', file=sys.stderr)
                output = BytesIO()
                if fmt == 'jpeg':
                    image = Image.new('RGB', im.size, 'white')
                    image.paste(im.convert('RGBA'), mask=im.convert('RGBA').getchannel('A'))
                else:
                    image = im
                kwargs = {'quality': compression if compression is not None else 95} if fmt != 'png' else {}
                image.save(output, format=FORMATS[fmt], **kwargs)
                data = output.getvalue()
        with Image.open(BytesIO(data)) as verified:
            if verified.format != FORMATS[fmt]:
                raise ValueError('local conversion failed')
            verified.verify()
        return data
    except (binascii.Error, UnidentifiedImageError, OSError) as exc:
        raise ValueError('invalid image result') from exc


def save_images(images: list[str], outputs: list[Path], *, fmt: str = 'png', force: bool = False, compression: int | None = None) -> None:
    if len(images) != len(outputs) or not outputs:
        raise ValueError('returned image count differs from requested count')
    if len(set(outputs)) != len(outputs):
        raise ValueError('duplicate output paths')
    decoded = [_decode_image(item, fmt, compression) for item in images]
    if not force and any(path.exists() for path in outputs):
        raise FileExistsError('output exists (use --force to replace)')
    for path, raw in zip(outputs, decoded):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.image2-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(raw)
            if force:
                os.replace(temporary, path)
            else:
                os.link(temporary, path)  # atomic create-if-absent
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        print(f'Wrote {path}')


def _config_dir() -> Path:
    override = os.environ.get('IMAGE2_CONFIG_DIR')
    if override:
        directory = Path(override).expanduser()
        if not directory.is_absolute():
            raise ValueError('IMAGE2_CONFIG_DIR must be an absolute directory')
        return directory
    if os.name == 'nt':
        # Keep credentials under the per-user local profile, not in the repository.
        local_app_data = os.environ.get('LOCALAPPDATA')
        return (Path(local_app_data) if local_app_data else Path.home() / 'AppData' / 'Local') / 'gpt-image-2-skill'
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'gpt-image-2-skill'


def _base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('base URL must be a plain HTTPS gateway URL without credentials/query')
    if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('remote gateway URL must use HTTPS')
    return value.strip().rstrip('/')


def _saved_config() -> dict:
    path = _config_dir() / 'config.json'
    if not path.is_file():
        raise ValueError('Image 2 gateway is unconfigured; run: image_gen_gateway.py configure --base-url https://YOUR-GATEWAY/v1')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('base_url'), str):
        raise ValueError('invalid Image 2 gateway config; run configure again')
    data['base_url'] = _base_url(data['base_url'])
    return data


def _write_private(path: Path, data: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.image2-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            out.write(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _configure(args: argparse.Namespace) -> int:
    base_url = _base_url(args.base_url)
    if args.key_env:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', args.key_env):
            raise ValueError('--key-env must be an environment variable name')
        key = os.environ.get(args.key_env)
        if not key:
            raise ValueError(f'{args.key_env} is unset; configure made no changes')
    else:
        if not sys.stdin.isatty():
            raise ValueError('run configure in a terminal to enter the key privately, or pass --key-env VARIABLE_NAME')
        key = getpass.getpass('Image 2 gateway key (hidden): ')
        if not key:
            raise ValueError('empty key; configure made no changes')
    directory = _config_dir()
    _write_private(directory / 'key', key.strip() + '\n')
    config = {'base_url': base_url}
    if args.host_model:
        config['host_model'] = args.host_model
    _write_private(directory / 'config.json', json.dumps(config, ensure_ascii=False) + '\n')
    print('Image 2 gateway configured (key hidden).')
    return 0


def _status() -> int:
    directory = _config_dir()
    config = _saved_config()
    has_key = bool(os.environ.get('IMAGE2_API_KEY') or
                   ((directory / 'key').is_file() and (directory / 'key').read_text().strip()))
    print(f'gateway={config["base_url"]} model={MODEL} key={"available" if has_key else "missing"}'
          f' host_model={config.get("host_model", "unset")}')
    return 0


def _credential() -> str:
    key = os.environ.get('IMAGE2_API_KEY')
    if key:
        return key
    path = _config_dir() / 'key'
    if path.is_file() and (key := path.read_text().strip()):
        return key
    raise ValueError('Image 2 gateway key unavailable; run configure again')


def _client():
    from openai import OpenAI
    config = _saved_config()
    return OpenAI(api_key=_credential(), base_url=config['base_url'], max_retries=0, timeout=240)


def _prompt(args: argparse.Namespace) -> str:
    if bool(args.prompt) == bool(args.prompt_file):
        raise ValueError('provide exactly one of --prompt or --prompt-file')
    value = Path(args.prompt_file).read_text().strip() if args.prompt_file else args.prompt.strip()
    if not value or len(value) > 32000:
        raise ValueError('prompt must be 1..32000 characters')
    return _augment_prompt(args, value)


def _outputs(args: argparse.Namespace, fmt: str) -> list[Path]:
    if getattr(args, 'out_dir', None):
        return [Path(args.out_dir) / f'image_{i}.{fmt}' for i in range(1, args.n + 1)]
    out = Path(args.out)
    if not out.suffix:
        out = out.with_suffix('.' + fmt)
    if out.suffix.lower() not in EXTENSIONS[fmt]:
        raise ValueError('output extension must match output-format')
    if args.n == 1:
        return [out]
    return [out.with_name(f'{out.stem}-{i}{out.suffix}') for i in range(1, args.n + 1)]


def _payload(args: argparse.Namespace) -> dict[str, Any]:
    validate_size(args.size)
    fmt = validate_output(args.background, args.output_format, args.output_compression)
    if args.quality not in ('auto', 'low', 'medium', 'high') or not 1 <= args.n <= 10:
        raise ValueError('quality must be auto/low/medium/high; n must be 1..10')
    if args.moderation not in (None, 'auto', 'low'):
        raise ValueError('moderation must be auto or low')
    if not 0 <= args.partial_images <= 3 or (args.partial_images and not args.stream):
        raise ValueError('partial-images requires --stream and value 0..3')
    if args.stream and args.n > 1:
        raise ValueError('stream with n>1 is not supported on this gateway; use separate calls')
    payload = dict(model=MODEL, prompt=_prompt(args), n=args.n, size=args.size,
                   quality=args.quality, output_format=fmt)
    for key in ('background', 'output_compression', 'moderation'):
        if getattr(args, key) is not None:
            payload[key] = getattr(args, key)
    if args.stream:
        payload.update(stream=True, partial_images=args.partial_images)
    return payload


def _downscale_paths(outputs: list[Path], args: argparse.Namespace) -> list[Path]:
    if args.downscale_max_dim is None:
        return []
    if args.downscale_max_dim < 1:
        raise ValueError('--downscale-max-dim must be >= 1')
    derived = [_derive_downscale_path(path, args.downscale_suffix) for path in outputs]
    if len(set(derived + outputs)) != len(derived + outputs):
        raise ValueError('downscale output collides with original output')
    return derived


def _postprocess(outputs: list[Path], fmt: str, args: argparse.Namespace) -> None:
    for source, dest in zip(outputs, _downscale_paths(outputs, args)):
        raw = _downscale_image_bytes(source.read_bytes(), max_dim=args.downscale_max_dim, output_format=fmt)
        if dest.exists() and not args.force:
            raise FileExistsError('downscale output exists')
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.image2-web-', dir=dest.parent)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(raw)
            if args.force:
                os.replace(temporary, dest)
            else:
                os.link(temporary, dest)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        print(f'Wrote {dest}')


def _run_one(args: argparse.Namespace, client=None) -> int:
    payload = _payload(args)
    fmt = payload['output_format']
    outputs = _outputs(args, fmt)
    derived = _downscale_paths(outputs, args)
    if not args.force and any(path.exists() for path in outputs + derived):
        raise FileExistsError('output exists (use --force to replace)')
    if args.stream and not args.force:
        preview_paths = [outputs[0].with_name(f'{outputs[0].stem}-partial-{i}{outputs[0].suffix}')
                         for i in range(1, args.partial_images + 1)]
        if any(path.exists() for path in preview_paths):
            raise FileExistsError('stream preview output exists (use --force to replace)')
    images = [Path(i) for i in getattr(args, 'image', [])]
    mask = Path(args.mask) if getattr(args, 'mask', None) else None
    if args.command == 'edit':
        validate_images(images, mask)
    if args.dry_run:
        print(json.dumps({'endpoint': '/v1/images/edits' if args.command == 'edit' else '/v1/images/generations',
                          'input_images': [str(p) for p in images], 'mask': str(mask) if mask else None,
                          'outputs': [str(p) for p in outputs], 'payload': payload}, ensure_ascii=False))
        return 0
    api = client if client is not None else _client()
    if args.command == 'edit':
        with ExitStack() as stack:
            opened = [stack.enter_context(path.open('rb')) for path in images]
            if mask:
                payload['mask'] = stack.enter_context(mask.open('rb'))
            payload['image'] = opened if len(opened) > 1 else opened[0]
            if args.n > 1:
                return _multi_call(api.images.edit, payload, outputs, fmt, args.force, args.output_compression, args)
            response = api.images.edit(**payload)
            return _consume(response, outputs, fmt, args.force, args.stream, args.partial_images, args.output_compression, args)
    if args.n > 1:
        return _multi_call(api.images.generate, payload, outputs, fmt, args.force, args.output_compression, args)
    response = api.images.generate(**payload)
    return _consume(response, outputs, fmt, args.force, args.stream, args.partial_images, args.output_compression, args)


def _multi_call(call, payload: dict, outputs: list[Path], fmt: str, force: bool, compression: int | None, args=None) -> int:
    print(f'Notice: n={len(outputs)} runs as {len(outputs)} single-image gateway requests', file=sys.stderr)
    singles = []
    for _ in outputs:
        for file in payload.get('image', []) if isinstance(payload.get('image'), list) else ([payload['image']] if 'image' in payload else []):
            file.seek(0)
        if 'mask' in payload:
            payload['mask'].seek(0)
        response = call(**{**payload, 'n': 1})
        data = getattr(response, 'data', None)
        if not data or len(data) != 1:
            raise ValueError('gateway did not return one image for single-image request')
        singles.append(getattr(data[0], 'b64_json', None))
    save_images(singles, outputs, fmt=fmt, force=force, compression=compression)
    if args is not None:
        _postprocess(outputs, fmt, args)
    return 0


def _consume(response, outputs: list[Path], fmt: str, force: bool, stream: bool, partial_count: int, compression: int | None = None, args=None) -> int:
    if not stream:
        result = [getattr(row, 'b64_json', None) for row in response.data]
    else:
        result, preview_count = [], 0
        for event in response:
            event_type = getattr(event, 'type', '')
            if event_type.endswith('.partial_image') and preview_count < partial_count:
                preview_count += 1
                base = outputs[0]
                dest = base.with_name(f'{base.stem}-partial-{preview_count}{base.suffix}')
                save_images([getattr(event, 'b64_json', None)], [dest],
                            fmt=fmt, force=force, compression=compression)
            elif event_type.endswith('.completed'):
                result.append(getattr(event, 'b64_json', None))
        if len(result) != len(outputs):
            raise ValueError('stream ended without all completed images')
    save_images(result, outputs, fmt=fmt, force=force, compression=compression)
    if args is not None:
        _postprocess(outputs, fmt, args)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Configurable gateway GPT Image 2; Images API plus optional Responses image tool.')
    subs = parser.add_subparsers(dest='command', required=True)
    configure = subs.add_parser('configure', help='one-time per-user gateway URL and key setup (no key in CLI arguments)')
    configure.add_argument('--base-url', required=True, help='HTTPS OpenAI-compatible base URL, including /v1')
    configure.add_argument('--key-env', help='read key once from this environment variable instead of private terminal prompt')
    configure.add_argument('--host-model', help='optional Responses host model for the tool subcommand')
    subs.add_parser('status', help='show gateway address and key availability, never key value')
    tool = subs.add_parser('tool', help='Responses API image tool (requires compatible mainline model)')
    tool.add_argument('--prompt', required=True)
    tool.add_argument('--image', action='append', default=[], help='local PNG/JPEG/WEBP, repeatable')
    tool.add_argument('--image-url', action='append', default=[], help='HTTPS image URL; provider must fetch it')
    tool.add_argument('--file-id', action='append', default=[], help='previously uploaded OpenAI file id')
    tool.add_argument('--previous-response-id')
    tool.add_argument('--mainline-model', help='Responses host model; defaults to configured host model or gpt-6-astra')
    tool.add_argument('--action', choices=('auto', 'generate', 'edit'))
    tool.add_argument('--size')
    tool.add_argument('--quality', choices=('auto', 'low', 'medium', 'high'))
    tool.add_argument('--background')
    tool.add_argument('--output-format')
    tool.add_argument('--output-compression', type=int)
    tool.add_argument('--out', default='output/imagegen/output.png')
    tool.add_argument('--force', action='store_true')
    tool.add_argument('--dry-run', action='store_true')
    tool.add_argument('--stream', action='store_true', help='stream image_generation_call events')
    tool.add_argument('--partial-images', type=int, default=0, help='0..3 preview frames (not guaranteed)')
    for name in ('generate', 'edit', 'generate-batch'):
        p = subs.add_parser(name)
        p.add_argument('--prompt')
        p.add_argument('--prompt-file')
        p.add_argument('--size', default='1024x1024')
        p.add_argument('--quality', default='auto')
        p.add_argument('--n', type=int, default=1)
        p.add_argument('--background')
        p.add_argument('--output-format', default='png')
        p.add_argument('--output-compression', type=int)
        p.add_argument('--moderation')
        p.add_argument('--out', default='output/imagegen/output.png')
        if name != 'generate-batch':
            p.add_argument('--out-dir')
        p.add_argument('--force', action='store_true')
        p.add_argument('--augment', dest='augment', action='store_true')
        p.add_argument('--no-augment', dest='augment', action='store_false')
        p.set_defaults(augment=True)
        for field in ('use-case', 'scene', 'subject', 'style', 'composition', 'lighting',
                      'palette', 'materials', 'text', 'constraints', 'negative'):
            p.add_argument('--' + field)
        p.add_argument('--downscale-max-dim', type=int)
        p.add_argument('--downscale-suffix', default='-web')
        p.add_argument('--dry-run', action='store_true')
        p.add_argument('--stream', action='store_true')
        p.add_argument('--partial-images', type=int, default=0)
        if name == 'edit':
            p.add_argument('--image', action='append', required=True, help='local source; repeat for references')
            p.add_argument('--mask', help='alpha PNG; first image is edit target')
        if name == 'generate-batch':
            p.add_argument('--input', required=True, help='JSONL: string prompt or object {prompt,...}')
            p.add_argument('--out-dir', required=True)
            p.add_argument('--concurrency', type=int, default=1)
    return parser


def _batch(args: argparse.Namespace, client=None) -> int:
    if not 1 <= args.concurrency <= 4:
        raise ValueError('batch concurrency must be 1..4')
    rows = [line.strip() for line in Path(args.input).read_text().splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not 1 <= len(rows) <= 500:
        raise ValueError('batch requires 1..500 jobs')
    jobs = []
    allowed = {'prompt', 'size', 'quality', 'n', 'background', 'output_format', 'output_compression',
               'moderation', 'out', 'augment', 'use_case', 'scene', 'subject', 'style',
               'composition', 'lighting', 'palette', 'materials', 'text', 'constraints',
               'negative', 'downscale_max_dim', 'downscale_suffix'}
    for i, line in enumerate(rows, 1):
        item = json.loads(line) if line.startswith('{') or line.startswith('"') else line
        item = {'prompt': item} if isinstance(item, str) else item
        if not isinstance(item, dict) or not set(item) <= allowed or not isinstance(item.get('prompt'), str):
            raise ValueError(f'job {i}: invalid fields')
        job = argparse.Namespace(**vars(args))
        job.command, job.prompt_file, job.out_dir = 'generate', None, None
        for key, value in item.items():
            setattr(job, key, value)
        fmt = validate_output(job.background, job.output_format, job.output_compression)
        job.out = str(Path(args.out_dir) / Path(item.get('out', f'image-{i}.{fmt}')).name)
        _payload(job)
        _outputs(job, validate_output(job.background, job.output_format, job.output_compression))
        jobs.append(job)
    paths = [p for job in jobs for p in (_outputs(job, validate_output(job.background, job.output_format, job.output_compression)) +
                                         _downscale_paths(_outputs(job, validate_output(job.background, job.output_format, job.output_compression)), job))]
    if len(paths) != len(set(paths)) or (not args.force and any(p.exists() for p in paths)):
        raise FileExistsError('batch output collision/existing file')
    if args.dry_run:
        for job in jobs:
            _run_one(job, client=client)
        return 0
    errors = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(_run_one, job, client) for job in jobs]
        for i, future in enumerate(futures, 1):
            try:
                future.result()
            except Exception as exc:
                errors.append((i, type(exc).__name__))
    if errors:
        raise ValueError(f'batch failed for jobs {errors}; no automatic retry')
    return 0


def _run_tool(args: argparse.Namespace, client=None) -> int:
    host_model = args.mainline_model or (_saved_config().get('host_model') if client is None else None) or 'gpt-6-astra'
    fmt = validate_output(args.background, args.output_format or 'png', args.output_compression)
    if not 0 <= args.partial_images <= 3 or (args.partial_images and not args.stream):
        raise ValueError('partial-images requires --stream and value 0..3')
    if args.size:
        validate_size(args.size)
    if not args.prompt.strip():
        raise ValueError('prompt is empty')
    if args.previous_response_id and not (args.image or args.image_url or args.file_id):
        raise ValueError('gateway does not restore prior image context by response ID; supply --image with the saved previous output')
    target = Path(args.out)
    if target.suffix.lower() not in EXTENSIONS[fmt]:
        raise ValueError('output extension must match output-format')
    if target.exists() and not args.force:
        raise FileExistsError('output exists (use --force to replace)')
    if args.stream and not args.force:
        preview_candidates = [target.with_name(f'{target.stem}-partial-{i}{target.suffix}') for i in range(4)]
        if any(path.exists() for path in preview_candidates):
            raise FileExistsError('stream preview output exists (use --force to replace)')
    content = [{'type': 'input_text', 'text': args.prompt}]
    for name in args.image:
        path = Path(name)
        with Image.open(path) as im:
            if im.format not in ('PNG', 'JPEG', 'WEBP'):
                raise ValueError('unsupported reference image format')
            image_fmt = 'jpeg' if im.format == 'JPEG' else im.format.lower()
            im.verify()
        encoded = base64.b64encode(path.read_bytes()).decode('ascii')
        content.append({'type': 'input_image', 'image_url': f'data:image/{image_fmt};base64,{encoded}'})
    for url in args.image_url:
        if not url.startswith('https://'):
            raise ValueError('image URL must use HTTPS')
        content.append({'type': 'input_image', 'image_url': url})
    for file_id in args.file_id:
        if not file_id.strip():
            raise ValueError('file ID cannot be empty')
        content.append({'type': 'input_image', 'file_id': file_id})
    tool = {'type': 'image_generation', 'model': MODEL}
    for key in ('action', 'size', 'quality', 'background', 'output_compression'):
        if getattr(args, key) is not None:
            tool[key] = getattr(args, key)
    if args.output_format is not None:
        tool['output_format'] = fmt
    if args.stream:
        tool['partial_images'] = args.partial_images
    if args.dry_run:
        print(json.dumps({'endpoint': '/v1/responses', 'mainline_model': host_model,
                          'tool': tool, 'stream': args.stream,
                          'input_images': len(content)-1, 'out': str(target)}))
        return 0
    payload = {'model': host_model, 'input': [{'role': 'user', 'content': content}],
               'tools': [tool], 'tool_choice': {'type': 'image_generation'}}
    if args.stream:
        payload['stream'] = True
    if args.previous_response_id:
        payload['previous_response_id'] = args.previous_response_id
    api = client or _client()
    result = api.responses.create(**payload)
    if args.stream:
        completed = None
        for event in result:
            kind = getattr(event, 'type', '')
            if kind == 'response.image_generation_call.partial_image':
                index = getattr(event, 'partial_image_index', None)
                if not isinstance(index, int) or index not in range(4):
                    raise ValueError('invalid partial image index')
                dest = target.with_name(f'{target.stem}-partial-{index}{target.suffix}')
                save_images([getattr(event, 'partial_image_b64', None)], [dest],
                            fmt=fmt, force=args.force, compression=args.output_compression)
            elif kind == 'response.completed':
                completed = getattr(event, 'response', None)
            elif kind == 'response.failed':
                raise ValueError('Responses stream failed without a final image')
        if completed is None:
            raise ValueError('Responses stream ended without a completed response')
        result = completed
    images = [getattr(item, 'result', None) for item in result.output
              if getattr(item, 'type', '') == 'image_generation_call']
    if not images:
        raise ValueError('Responses API did not return an image_generation_call')
    if len(images) != 1:
        raise ValueError('Responses API returned an unexpected number of images')
    save_images(images, [target], fmt=fmt, force=args.force, compression=args.output_compression)
    print(f'response_id={getattr(result, "id", "unavailable")}')
    return 0


def main(argv=None, *, client=None) -> int:
    args = _parser().parse_args(argv)
    if args.command == 'configure':
        return _configure(args)
    if args.command == 'status':
        return _status()
    if args.command == 'tool':
        return _run_tool(args, client=client)
    return _batch(args, client=client) if args.command == 'generate-batch' else _run_one(args, client=client)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # API errors can include request bodies/IDs; never print their string representation.
        if isinstance(exc, (ValueError, FileExistsError, FileNotFoundError)):
            print(f'Error: {exc}', file=sys.stderr)
        else:
            status = getattr(exc, 'status_code', None)
            body = getattr(exc, 'body', None)
            code = body.get('code') if isinstance(body, dict) else None
            code = code if isinstance(code, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', code) else None
            print(f'Error: {type(exc).__name__} status={status or "unknown"} code={code or "none"} (no provider fallback)', file=sys.stderr)
        raise SystemExit(1)
