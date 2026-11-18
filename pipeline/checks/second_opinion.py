"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


def run(ds, cfg, preds=None):
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    sc = cfg.get("second_opinion", {})
    conf_min = float(sc.get("conf", 0.25))
    min_area = float(sc.get("min_area_px", 0))
    fp_conf = float(sc.get("fp_conf", 0.1))
    iou_missing = float(sc.get("iou_missing", 0.3))
    iou_match = float(sc.get("iou_match", 0.5))
    iou_loose = float(sc.get("iou_loose", 0.5))
    out = []

    for image_path in ds.image_files():
        stem = image_path.stem
        if stem not in preds or ds.read_label_lines(stem) is None:
            continue
        size = ds.image_size(stem)
        if size is None:
            continue
        width, height = size

        labels = []
        for line_no, text in ds.read_label_lines(stem) or []:
            try:
                label = parse_yolo_line(text)
            except ValueError:
                continue
            if 0 <= label[0] < len(ds.classes) and label[3] > 0 and label[4] > 0:
                labels.append((line_no, label[0], label[1:]))

        all_predictions = []
        useful_predictions = []
        for row in preds.get(stem, []):
            try:
                pcls, pconf, pcx, pcy, pw, ph = row
                pcls, pconf = int(pcls), float(pconf)
                pbox = (float(pcx), float(pcy), float(pw), float(ph))
            except (TypeError, ValueError):
                continue
            all_predictions.append((pcls, pconf, pbox))
            if pconf >= conf_min and pw * width * ph * height >= min_area:
                useful_predictions.append((pcls, pconf, pbox))

        for pcls, pconf, pbox in useful_predictions:
            cands = [(line, cls, box, iou_xywh(pbox, box)) for line, cls, box in labels
                     if iou_xywh(pbox, box) >= iou_missing]
            if not cands:
                out.append(Issue("second_opinion", WARN, "POSSIBLE_MISSING", stem,
                                 "Model thấy vật thể nhưng nhãn không có box khớp",
                                 extra={"conf": pconf}))
                continue

            same = [c for c in cands if c[1] == pcls]
            if same:
                best = max(same, key=lambda c: c[3])
                if best[3] < iou_loose:
                    out.append(Issue("second_opinion", WARN, "POSSIBLE_LOOSE_BOX", stem,
                                     "Box nhãn cùng lớp nhưng có vẻ lỏng hoặc lệch",
                                     extra={"iou": best[3], "conf": pconf}))
                continue

            other = max(cands, key=lambda c: c[3])
            if other[3] >= iou_match:
                out.append(Issue("second_opinion", WARN, "POSSIBLE_WRONG_CLASS", stem,
                                 "Model và nhãn có vẻ gán khác lớp cho cùng một vật",
                                 extra={"iou": other[3], "conf": pconf}))

        for line_no, label_cls, label_box in labels:
            matched = any(
                iou_xywh(label_box, pbox) >= iou_missing
                for _, pconf, pbox in all_predictions if pconf >= fp_conf
            )
            if not matched:
                out.append(Issue("second_opinion", WARN, "POSSIBLE_FALSE_POS", stem,
                                 "Box nhãn không khớp dự đoán nào của model",
                                 line=line_no))
    return out
