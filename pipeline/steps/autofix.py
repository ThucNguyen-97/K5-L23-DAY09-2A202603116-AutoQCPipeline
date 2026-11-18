"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


def fix(ds, issues, cfg):
    drop_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
    remove_codes = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
    by_image = defaultdict(list)
    fixes = []
    for issue in issues:
        if issue.severity != ERROR:
            continue
        if issue.code == "MISSING_LABEL_FILE":
            fixes.append({"image": issue.image, "line": issue.line, "action": "needs_label",
                          "before": "(không có file)", "after": "chuyển người gán"})
        elif issue.code == "BAD_CLASS_NAME":
            if ds.yaml_path.exists():
                data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
                data["names"] = list(cfg["classes"])
                ds.yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            fixes.append({"image": "data.yaml", "line": None, "action": "rename_classes",
                          "before": "(tên lớp cũ)", "after": ", ".join(cfg["classes"])})
        elif issue.code in remove_codes:
            if issue.image not in {f["image"] for f in fixes if f["action"] == "remove_image"}:
                image = ds.image_path(issue.image)
                label = ds.label_path(issue.image)
                if image is not None:
                    image.unlink(missing_ok=True)
                label.unlink(missing_ok=True)
                fixes.append({"image": issue.image, "line": None, "action": "remove_image",
                              "before": "(ảnh và nhãn)", "after": "đã xoá"})
        elif issue.line is not None:
            by_image[issue.image].append(issue)

    for stem, image_issues in by_image.items():
        path = ds.label_path(stem)
        if not path.exists():
            continue
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        by_line = defaultdict(list)
        for issue in image_issues:
            by_line[issue.line].append(issue)
        new_lines = []
        for line_no, raw in enumerate(raw_lines, 1):
            line_issues = by_line.get(line_no, [])
            if any(i.code in drop_codes for i in line_issues):
                fixes.append({"image": stem, "line": line_no, "action": "drop_line",
                              "before": raw, "after": ""})
                continue
            clip_issue = next((i for i in line_issues if i.code == "BOX_OUT_OF_IMAGE"), None)
            if clip_issue is not None:
                try:
                    cls, cx, cy, w, h = parse_yolo_line(raw)
                    left, top = max(0.0, cx - w / 2), max(0.0, cy - h / 2)
                    right, bottom = min(1.0, cx + w / 2), min(1.0, cy + h / 2)
                    nw, nh = right - left, bottom - top
                    if nw <= 0 or nh <= 0:
                        fixes.append({"image": stem, "line": line_no, "action": "drop_line",
                                      "before": raw, "after": ""})
                        continue
                    after = f"{cls} {(left + right) / 2:.6g} {(top + bottom) / 2:.6g} {nw:.6g} {nh:.6g}"
                    new_lines.append(after)
                    fixes.append({"image": stem, "line": line_no, "action": "clip_box",
                                  "before": raw, "after": after})
                    continue
                except ValueError:
                    pass
            new_lines.append(raw)
        path.write_text("\n".join(new_lines) + ("\n" if raw_lines else ""), encoding="utf-8")
    return fixes
