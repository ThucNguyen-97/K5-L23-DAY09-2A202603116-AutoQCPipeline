# Báo cáo Day 09 — Nguyen Quang Thuc, 2A202603116

> Mỗi ý trả lời bằng **số lấy từ `submission/reports/`**, kèm mẫu số. Cả báo cáo ~1–2 trang.

## 1. Kết luận trước
Pipeline kết luận **Hold**. Có 224 ảnh đầu vào; 21 ảnh bị loại ngay ở bước intake, còn 203 ảnh được nhận vào pipeline và bản export `clean_v1` có 203 ảnh (bản nháp để tiếp tục xử lý). 21 ảnh bị loại gồm: 3 ảnh không đạt kích thước tối thiểu (`BAD_SIZE`), 2 ảnh hỏng không đọc được (`CORRUPT_IMAGE`), 8 ảnh trùng byte (`DUP_IMAGE_EXACT`), 3 ảnh trùng gần (`DUP_IMAGE_NEAR`) và 5 ảnh trùng tập test/validation (`LEAK_TEST`). Sau mô phỏng review 80 ảnh, còn 38/203 ảnh có cảnh báo, tương đương 18.72%, cao hơn ngưỡng Release 10.00%; không còn lỗi bắt buộc (`n_errors=0`), nên gate kết luận Hold.

## 2. Lỗi và phân việc
Lấy từ `02_error_list_v1` (gom theo mã lỗi). Cột "ai sửa": **máy** (autofix) hay **người** (hàng đợi); chỉ ghi những mã có mặt trong lô của bạn.

| Mã lỗi | Số ảnh/dòng | Ai sửa (máy/người) | Vì sao |
|---|---:|---|---|
| BAD_CLASS_ID | 6 dòng | máy | ID lớp ngoài danh sách; dòng lỗi được loại/sửa theo autofix. |
| BAD_CLASS_NAME | 2 dòng | máy | Chuẩn hoá tên lớp trong `data.yaml`. |
| BAD_FORMAT | 3 dòng | máy | Loại dòng YOLO sai định dạng hoặc chứa NaN/Inf. |
| BOX_OUT_OF_IMAGE | 8 dòng | máy | Clip box về biên ảnh. |
| BOX_ZERO | 4 dòng | máy | Loại box có kích thước không dương. |
| DUP_BOX | 7 dòng | máy | Loại box trùng trong cùng file nhãn. |
| MISSING_LABEL_FILE | 6 ảnh | người | Chuyển sang hàng đợi để người gán nhãn. |
| DUP_IMAGE_EXACT / NEAR | 11 ảnh | máy + người | Loại ảnh trùng chắc chắn; near-duplicate cần đối chiếu. |
| LEAK_TEST | 5 ảnh | máy | Loại ảnh trùng tập test/val. |
| BOX_HUGE / BOX_TINY | 3 / 6 dòng | người | Cảnh báo hình học, không tự xoá vì có thể là vật thể thật. |
| POSSIBLE_MISSING | 53 dòng | người | Model thấy vật thể nhưng chưa khớp box nhãn. |
| POSSIBLE_WRONG_CLASS | 18 dòng | người | Model và nhãn khác lớp trên cùng vùng. |
| POSSIBLE_LOOSE_BOX / FALSE_POS | 28 / 24 dòng | người | Cảnh báo chất lượng box và box không khớp dự đoán. |

Hàng đợi `05_review_queue.csv` ưu tiên lỗi bắt buộc, ảnh thiếu nhãn và các cảnh báo có mức ảnh hưởng cao; trong ngân sách 80, toàn bộ 80 lượt review đã được sử dụng. Sau review còn 4 EMPTY_LABEL, 13 POSSIBLE_MISSING, 3 POSSIBLE_WRONG_CLASS, 20 POSSIBLE_LOOSE_BOX và 21 POSSIBLE_FALSE_POS ở mức cảnh báo.

## 3. Calibration (2 ngưỡng)
| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | 6 | DUP_IMAGE_NEAR: 1.00 / 0.50 / 0.67 → 1.00 / 0.67 / 0.80 | Chọn 6 để ưu tiên precision cho thao tác loại ảnh; các cặp raw ở khoảng cách 6 vẫn là cùng cảnh khi kiểm tra trực quan. |
| `second_opinion.conf` | 0.25 | 0.6 | WRONG_CLASS: 0.56 / 0.83 / 0.67 → 0.62 / 0.83 / 0.71; MISSING: 0.50 / 1.00 / 0.67 → 0.57 / 1.00 / 0.73 | Tăng precision nhưng vẫn giữ recall cao cho lỗi thiếu nhãn và nhầm lớp. |

Calibration có thể đánh lừa vì bộ calib chỉ có 39 ảnh và lỗi chèn khá rõ ràng. Khi kiểm tra raw, hai cặp ở khoảng cách 16 (`img_0008↔img_0011` và `img_0113↔img_0177`) là hai cảnh hoàn toàn khác nhau; vì vậy không chọn 16 dù recall trên calib cao hơn. Ngưỡng 6 bảo thủ hơn để tránh xoá nhầm ảnh tốt. Ngoài ra, `second_opinion` vẫn có precision thấp ở `POSSIBLE_FALSE_POS` (0.36), nên đây là cảnh báo cho người duyệt chứ không phải bằng chứng nhãn chắc chắn sai.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
Gate được kiểm chứng bằng `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`: kết luận **Rework**, mã thoát **20**, còn 6 lỗi bắt buộc và `exported=null`, tức không xuất dataset. Hai điểm mù có bằng chứng là cảnh báo `POSSIBLE_LOOSE_BOX` vẫn còn nhiều sau review (20 dòng), và `second_opinion` vẫn để lại `POSSIBLE_FALSE_POS` (21 dòng), vì dự đoán model không phải ground truth. Ngoài ra, phash ở khoảng cách 16 tạo false positive trên hai cặp cảnh khác nhau nên đã chọn ngưỡng bảo thủ 6.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Đã train công bằng trên Colab: cùng `yolo26n.pt`, 20 epoch, batch 16, `imgsz=640`, cùng tập val/test, cùng `config_sha1` và hai seed `0,1`. Raw có 224 ảnh đầu vào; clean có 203 ảnh theo manifest.

| Biến thể | mAP50 (TB ± SD) | mAP50-95 (TB ± SD) | Precision | Recall |
|---|---:|---:|---:|---:|
| raw | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 0.699 ± 0.025 | 0.486 ± 0.013 | 0.796 ± 0.050 | 0.596 ± 0.049 |

Chênh lệch mAP50 `clean - raw = -0.027`, nhỏ hơn độ lệch giữa seed của clean (SD 0.025) nhưng lớn hơn SD của raw (0.000). Vì chỉ có 2 seed và clean còn cảnh báo, chưa thể kết luận việc làm sạch làm chất lượng model tốt hơn; kết quả này chỉ cho thấy clean tăng precision trung bình nhưng giảm recall và mAP trên tập test ở thí nghiệm hiện tại. Theo lớp, clean gần như không đổi ở car/person/bus, còn truck giảm khoảng 0.113 AP50 (0.648 → 0.536).

Hai giả thuyết cần kiểm tra thêm: (1) raw có 5 ảnh trùng test/val (`LEAK_TEST`), có thể làm điểm raw bị thổi phồng; kiểm bằng hash ảnh raw với `data/test` và `data/gold_val`; (2) clean loại ảnh trùng, lỗi kích thước/hỏng và sửa nhãn, đồng thời vẫn còn cảnh báo thiếu box/box lỏng, nên giảm recall hoặc làm mất các mẫu truck; kiểm bằng thống kê ảnh/box theo lớp và review các ảnh truck bị loại trong `01_intake.csv`, `02_error_list_v1.csv`.

## 6. Quyết định và ghi chú AI
Quyết định cuối: **Hold**. Để thành Release cần review/sửa các cảnh báo còn lại, chạy lại pipeline và đưa tỷ lệ ảnh cảnh báo xuống không quá 10%; nếu phát sinh lỗi bắt buộc thì phải quay về Rework.

Đã dùng AI hỗ trợ viết code: (1) prompt chính là triển khai các module QC, pipeline và extension review duplicate theo README; (2) kiểm bằng unit test, calibration, chạy pipeline, kiểm gate budget 0 và kiểm thử CVAT local; (3) AI từng chọn phash 16 theo điểm calib, nhưng kiểm tra trực quan phát hiện false positive nên đã hạ xuống 6.

*(Thưởng +2, tùy chọn)* CVAT: lọc `width < 20`, ảnh/số box khớp, đối chiếu `BOX_TINY` (xem docs/CVAT_FILTER.md), 1 câu về `can_review`.
