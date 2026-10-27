"""Preserve supplied images; account for every input before generating missing slots."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

from _local_paths import contained_path, image_id


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(post, files):
    post = Path(post)
    target = post / 'user-assets.json'
    if target.exists():
        raise ValueError('기존 이미지 목록을 덮어쓰지 않습니다. 목록에 새 항목을 추가하세요')
    assets = []
    for index, value in enumerate(files, 1):
        path = Path(value).resolve(strict=True)
        assets.append(dict(id=f'user-{index}', path=str(path), sha256=digest(path),
                           decision='pending', reason='', sticker_ids=[]))
    post.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'assets': assets}, ensure_ascii=False, indent=2), encoding='utf-8')
    return target


def validate(post, plan, catalog):
    if not plan.get('images') or not any(im.get('type') == 'thumbnail' for im in plan['images']):
        raise ValueError('THUMBNAIL: 썸네일 자리가 필요합니다')
    if plan.get('thumbnail_format') not in ('square', 'landscape'):
        raise ValueError('THUMB_FORMAT: 썸네일 비율을 사용자에게 먼저 질문하세요')
    for im in plan['images']:
        if im.get('type') not in ('thumbnail', 'steps', 'compare', 'checklist', 'keypoint', 'stats'):
            raise ValueError('알 수 없는 이미지 type')
        if not im.get('alt', '').strip():
            raise ValueError('ALT: ' + im['id'])
    path = Path(post) / 'user-assets.json'
    if not path.is_file():
        raise ValueError('USER_ASSETS_REQUIRED: 첨부 이미지 목록이 필요합니다. 없으면 assets: []로 명시하세요')
    assets = json.loads(path.read_text(encoding='utf-8-sig'))['assets']
    seen, reused = set(), {}
    used_stickers = set()
    for image in plan['images']:
        used_stickers.add(image.get('character'))
        used_stickers.add((image.get('bubble') or {}).get('sticker'))
        for prop in image.get('props', []):
            used_stickers.add(prop if isinstance(prop, str) else prop.get('id'))
    for asset in assets:
        aid = image_id(asset['id'])
        if aid in seen:
            raise ValueError('중복 사용자 이미지 id: ' + aid)
        seen.add(aid)
        decision = asset.get('decision')
        if decision not in ('reuse', 'sticker', 'reference', 'skip'):
            raise ValueError('USER_ASSET_UNRESOLVED: ' + aid)
        source = Path(asset['path']).resolve(strict=True)
        if digest(source) != asset['sha256']:
            raise ValueError('USER_ASSET_CHANGED: ' + aid)
        if decision in ('skip', 'reference') and not asset.get('reason', '').strip():
            raise ValueError('사용자 이미지 미배치 사유가 필요합니다: ' + aid)
        if decision == 'reuse':
            slots = [im for im in plan['images'] if im.get('asset_id') == aid]
            if not slots:
                raise ValueError('USER_ASSET_UNUSED: ' + aid)
            from PIL import Image
            with Image.open(source) as im:
                im.verify()
            with Image.open(source) as im:
                w, h = im.size
            for slot in slots:
                ratio = 1 if slot['type'] == 'thumbnail' and slot.get('format', plan.get('thumbnail_format')) == 'square' else 16 / 9
                if abs(w / h - ratio) > .05:
                    raise ValueError('USER_ASSET_RATIO: 원본을 왜곡하지 않습니다. 적합한 자리에 배치하거나 사용자와 조정하세요: ' + aid)
                if not slot.get('alt', '').strip():
                    raise ValueError('ALT: ' + aid)
                reused[slot['id']] = dict(source=source, asset_id=aid, sha256=asset['sha256'], size=[w, h])
        if decision == 'sticker':
            ids = asset.get('sticker_ids', [])
            if not ids or not set(ids).issubset(catalog) or not set(ids).intersection(used_stickers):
                raise ValueError('USER_STICKER_UNUSED: 가져온 스티커 id를 실제 계획에 사용하세요: ' + aid)
    if any(im.get('asset_id') not in seen for im in plan['images'] if im.get('asset_id')):
        raise ValueError('알 수 없는 사용자 이미지 asset_id')
    if any(im.get('asset_id') and im['id'] not in reused for im in plan['images']):
        raise ValueError('asset_id는 reuse로 판정한 이미지에만 사용할 수 있습니다')
    return reused, assets


def copy_reused(out, reused, plan):
    result = {}
    for im in plan['images']:
        if im['id'] not in reused:
            continue
        asset = reused[im['id']]
        ext = asset['source'].suffix.lower()
        if ext not in ('.png', '.jpg', '.jpeg', '.webp', '.gif'):
            raise ValueError('지원하지 않는 사용자 이미지 형식: ' + ext)
        name = image_id(im['id']) + ext
        target = Path(contained_path(out, name))
        if target.resolve() != asset['source']:
            shutil.copy2(asset['source'], target)
        result[im['id']] = dict(type=im['type'], file='visuals/' + name, alt=im['alt'],
                                format=plan.get('thumbnail_format') if im['type'] == 'thumbnail' else 'landscape',
                                size=asset['size'], stickers=[], source_kind='user',
                                asset_id=asset['asset_id'], source_sha256=asset['sha256'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='사용자 제공 이미지 원본과 해시 기록; 이미지 생성은 하지 않음')
    parser.add_argument('--post', required=True)
    parser.add_argument('--file', action='append', default=[])
    args = parser.parse_args()
    print(inventory(args.post, args.file))
