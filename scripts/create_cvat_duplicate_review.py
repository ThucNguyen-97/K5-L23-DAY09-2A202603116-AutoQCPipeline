"""Create a CVAT review task for duplicate-image candidates.

The command is intentionally useful offline first:

    python scripts/create_cvat_duplicate_review.py \
        --src data/raw --out work/cvat_duplicate_review

It creates one contact-sheet image per candidate pair, a CSV/JSON manifest,
and a CVAT task specification.  With ``--upload`` it can also create a task
through the CVAT REST API using ``CVAT_URL`` and ``CVAT_TOKEN``.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.checks.duplicates import run as duplicate_check  # noqa: E402
from pipeline.common import Dataset, load_config  # noqa: E402

REVIEW_LABELS = [
    {"name": "DUPLICATE_KEEP_LEFT", "type": "any", "color": "#e11d48"},
    {"name": "DUPLICATE_KEEP_RIGHT", "type": "any", "color": "#2563eb"},
    {"name": "DUPLICATE_KEEP_BOTH", "type": "any", "color": "#16a34a"},
    {"name": "NOT_DUPLICATE", "type": "any", "color": "#f59e0b"},
]


def _open_image(ds: Dataset, stem: str) -> Image.Image:
    path = ds.image_path(stem)
    if path is None:
        raise FileNotFoundError(f"Không tìm thấy ảnh {stem}")
    with Image.open(path) as im:
        return im.convert("RGB")


def _panel(ds: Dataset, left: str, right: str, code: str, dist, out: Path) -> None:
    """Render two images side by side with stable pair metadata in the pixels."""
    thumb_w, thumb_h = 640, 480
    header_h = 64
    canvas = Image.new("RGB", (thumb_w * 2, thumb_h + header_h), "white")
    draw = ImageDraw.Draw(canvas)
    for x, stem in ((0, left), (thumb_w, right)):
        im = ImageOps.contain(_open_image(ds, stem), (thumb_w, thumb_h))
        px = x + (thumb_w - im.width) // 2
        py = header_h + (thumb_h - im.height) // 2
        canvas.paste(im, (px, py))
        draw.rectangle((x, header_h, x + thumb_w - 1, header_h + thumb_h - 1), outline="#475569", width=2)
    draw.text((12, 10), f"LEFT: {left}", fill="#111827")
    draw.text((thumb_w + 12, 10), f"RIGHT: {right}", fill="#111827")
    draw.text((12, 38), f"{code} | phash distance: {dist if dist is not None else 'exact'}", fill="#475569")
    canvas.save(out, quality=92)


def build_bundle(src: str | Path, out: str | Path, config: str | Path | None = None) -> dict:
    cfg = load_config(ROOT / config if config else None)
    ds = Dataset(ROOT / src, cfg["classes"])
    out_dir = ROOT / out
    image_dir = out_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    issues = duplicate_check(ds, cfg)
    candidates = [i for i in issues if i.code in {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR"} and i.extra.get("of")]
    rows = []
    for index, issue in enumerate(candidates, 1):
        pair_id = f"pair_{index:04d}"
        left, right = str(issue.extra["of"]).split("/", 1)[-1].rsplit(".", 1)[0], issue.image
        # Internal duplicate references are stems.  The checker's `of` value
        # for internal pairs is a stem; only use the final path component.
        left = Path(str(issue.extra["of"])).stem
        panel_name = f"{pair_id}__{left}__{right}.jpg"
        _panel(ds, left, right, issue.code, issue.extra.get("dist"), image_dir / panel_name)
        rows.append({
            "pair_id": pair_id,
            "image": panel_name,
            "left_image": left,
            "right_image": right,
            "reason": issue.code,
            "phash_distance": issue.extra.get("dist", ""),
            "review_decision": "",
            "review_note": "",
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "duplicate_pairs.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else [
            "pair_id", "image", "left_image", "right_image", "reason",
            "phash_distance", "review_decision", "review_note",
        ])
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / "duplicate_pairs.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    spec = {
        "name": f"Day09 Duplicate Review ({len(rows)} pairs)",
        "labels": REVIEW_LABELS,
        "image_count": len(rows),
        "source": str(src),
        "phash_dist": cfg["duplicates"]["phash_dist"],
        "review_instructions": "Mỗi frame là một cặp ảnh. Gán đúng một tag: giữ trái, giữ phải, giữ cả hai, hoặc không trùng.",
    }
    (out_dir / "cvat_task_spec.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"out": str(out_dir), "pairs": len(rows), "spec": spec}


def upload_to_cvat(bundle: dict, cvat_url: str, token: str, task_name: str | None = None) -> int:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("Cần cài requests để upload: python -m pip install requests") from exc

    out_dir = Path(bundle["out"])
    labels = [{"name": x["name"], "type": x["type"], "attributes": []} for x in REVIEW_LABELS]
    headers = {"Authorization": f"Token {token}"}
    base = cvat_url.rstrip("/")
    response = requests.post(
        f"{base}/api/tasks",
        headers=headers,
        json={"name": task_name or bundle["spec"]["name"], "labels": labels},
        timeout=60,
    )
    response.raise_for_status()
    task_id = response.json()["id"]

    files = []
    handles = []
    try:
        for path in sorted((out_dir / "images").glob("*.jpg")):
            handle = path.open("rb")
            handles.append(handle)
            files.append(("client_files[]", (path.name, handle, "image/jpeg")))
        data_response = requests.post(
            f"{base}/api/tasks/{task_id}/data",
            headers=headers,
            files=files,
            data={"image_quality": 90, "sorting_method": "lexicographical"},
            timeout=120,
        )
        data_response.raise_for_status()
    except Exception:
        requests.delete(f"{base}/api/tasks/{task_id}", headers=headers, timeout=30)
        raise
    finally:
        for handle in handles:
            handle.close()
    return int(task_id)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default="data/raw", help="dataset kiểu YOLO")
    ap.add_argument("--out", default="work/cvat_duplicate_review", help="thư mục bundle")
    ap.add_argument("--config", default="configs/pipeline.yaml")
    ap.add_argument("--upload", action="store_true", help="tạo task trên CVAT sau khi tạo bundle")
    ap.add_argument("--cvat-url", default=os.environ.get("CVAT_URL"))
    ap.add_argument("--token", default=os.environ.get("CVAT_TOKEN"))
    ap.add_argument("--task-name")
    args = ap.parse_args(argv)
    bundle = build_bundle(args.src, args.out, args.config)
    print(f"Đã tạo {bundle['pairs']} cặp review tại {bundle['out']}")
    if args.upload:
        if not args.cvat_url or not args.token:
            ap.error("--upload cần CVAT_URL/--cvat-url và CVAT_TOKEN/--token")
        task_id = upload_to_cvat(bundle, args.cvat_url, args.token, args.task_name)
        print(f"Đã tạo CVAT task: {task_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
