"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    out = []
    lc = cfg.get("label_format", {})
    tol = float(lc.get("overflow_tol", 0.0))
    dup_iou = float(lc.get("dup_box_iou", 0.9))
    min_box_px = float(lc.get("min_box_px", 0))
    max_box_frac = float(lc.get("max_box_frac", 1.0))

    for path in ds.label_files():
        stem = path.stem
        size = ds.image_size(stem)
        prior = []
        for line_no, text in ds.read_label_lines(stem) or []:
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except ValueError as exc:
                out.append(Issue("label_format", ERROR, "BAD_FORMAT", stem,
                                 f"Dòng {line_no} sai định dạng: {exc}", line_no))
                continue

            if not 0 <= cls < len(ds.classes):
                out.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem,
                                 f"ID lớp {cls} không hợp lệ", line_no))
                continue
            if w <= 0 or h <= 0:
                out.append(Issue("label_format", ERROR, "BOX_ZERO", stem,
                                 "Chiều rộng hoặc chiều cao box không dương", line_no))
                continue

            box = (cx, cy, w, h)
            left, top = cx - w / 2, cy - h / 2
            right, bottom = cx + w / 2, cy + h / 2
            overflow = max(0.0, -left, -top, right - 1.0, bottom - 1.0)
            if overflow > tol:
                out.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                                 f"Box tràn ảnh {overflow:.6g}", line_no,
                                 {"overflow": overflow}))

            if size is not None and min(w * size[0], h * size[1]) < min_box_px:
                out.append(Issue("label_format", WARN, "BOX_TINY", stem,
                                 f"Cạnh ngắn của box nhỏ hơn {min_box_px:g}px", line_no))
            if w * h > max_box_frac:
                out.append(Issue("label_format", WARN, "BOX_HUGE", stem,
                                 f"Diện tích box lớn hơn {max_box_frac:g}", line_no))

            for old_cls, old_box, old_line in prior:
                if old_cls == cls and iou_xywh(box, old_box) > dup_iou:
                    out.append(Issue("label_format", ERROR, "DUP_BOX", stem,
                                     f"Box trùng với dòng {old_line}", line_no,
                                     {"iou": iou_xywh(box, old_box)}))
                    break
            prior.append((cls, box, line_no))
    return out
