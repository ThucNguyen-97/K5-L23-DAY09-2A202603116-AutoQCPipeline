# Phân tích train raw vs clean

Thí nghiệm dùng cùng `yolo26n.pt`, 20 epoch, batch 16, `imgsz=640`, cùng tập validation/test và hai seed `0,1`. Raw có 224 ảnh; clean có 203 ảnh theo `submission/export/clean_v1/manifest.json`.

| Biến thể | mAP50 | mAP50-95 | Precision | Recall |
|---|---:|---:|---:|---:|
| raw | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 0.699 ± 0.025 | 0.486 ± 0.013 | 0.796 ± 0.050 | 0.596 ± 0.049 |

Chênh lệch mAP50 của clean so với raw là `-0.027`. Với chỉ 2 seed, chưa đủ cơ sở để kết luận clean kém hơn một cách ổn định: clean tăng precision nhưng giảm recall, và vẫn còn cảnh báo do pipeline kết luận Hold.

Theo lớp, chênh AP50 của clean − raw là: car `+0.003`, person `+0.002`, truck `-0.113`, bus `-0.000`. Truck là lớp bị ảnh hưởng rõ nhất.

Các giả thuyết cần kiểm tra thêm:

1. Raw có 5 ảnh trùng tập test/validation (`LEAK_TEST`), nên điểm raw có thể bị thổi phồng. Kiểm bằng hash ảnh raw với `data/test` và `data/gold_val`.
2. Clean loại ảnh trùng, ảnh hỏng/kích thước sai và sửa nhãn, nhưng vẫn còn cảnh báo thiếu box/box lỏng. Kiểm bằng thống kê box theo lớp và đối chiếu các ảnh truck bị loại trong `01_intake.csv` và `02_error_list_v1.csv`.

Kết luận: thí nghiệm chưa chứng minh clean cải thiện mAP50; cần xử lý thêm cảnh báo và chạy nhiều seed hơn trước khi kết luận về lợi ích của pipeline.
