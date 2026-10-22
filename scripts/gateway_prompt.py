"""Prompt/thumbnail helpers adapted from OpenAI's Apache-2.0 imagegen skill.

Modified for this standalone gateway implementation; see NOTICE and LICENSE.
"""
from io import BytesIO
from pathlib import Path

from PIL import Image


LABELS = (
    ('use_case', 'Use case'), ('scene', 'Scene/background'),
    ('subject', 'Subject'), ('style', 'Style/medium'),
    ('composition', 'Composition/framing'), ('lighting', 'Lighting/mood'),
    ('palette', 'Color palette'), ('materials', 'Materials/textures'),
    ('text', 'Text (verbatim)'), ('constraints', 'Constraints'),
    ('negative', 'Avoid'),
)


def _augment_prompt(args, prompt):
    if not args.augment:
        return prompt
    lines = []
    if getattr(args, 'use_case', None):
        lines.append(f'Use case: {args.use_case}')
    lines.append(f'Primary request: {prompt}')
    for key, label in LABELS[1:]:
        value = getattr(args, key, None)
        if value:
            lines.append(f'{label}: "{value}"' if key == 'text' else f'{label}: {value}')
    return '\n'.join(lines)


def _derive_downscale_path(path: Path, suffix: str) -> Path:
    if suffix and not suffix.startswith(('-', '_')):
        suffix = '-' + suffix
    return path.with_name(f'{path.stem}{suffix}{path.suffix}')


def _downscale_image_bytes(data: bytes, *, max_dim: int, output_format: str) -> bytes:
    if max_dim < 1:
        raise ValueError('--downscale-max-dim must be >= 1')
    with Image.open(BytesIO(data)) as source:
        source.load()
        width, height = source.size
        factor = min(1.0, max_dim / max(width, height))
        target = (max(1, round(width * factor)), max(1, round(height * factor)))
        resized = source if target == source.size else source.resize(target, Image.Resampling.LANCZOS)
        fmt = output_format.lower().replace('jpg', 'jpeg')
        if fmt == 'jpeg':
            if resized.mode in ('RGBA', 'LA') or 'transparency' in resized.info:
                rgba = resized.convert('RGBA')
                opaque = Image.new('RGB', resized.size, 'white')
                opaque.paste(rgba, mask=rgba.getchannel('A'))
                resized = opaque
            else:
                resized = resized.convert('RGB')
        output = BytesIO()
        resized.save(output, format=fmt.upper())
        return output.getvalue()
