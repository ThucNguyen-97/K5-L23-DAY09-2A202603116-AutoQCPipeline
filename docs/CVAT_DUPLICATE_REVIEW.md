# CVAT Duplicate Review Extension

Tool này biến các cặp ảnh bị `duplicates` đánh dấu thành một CVAT review task.
Mỗi frame trong task là một contact sheet gồm ảnh trái và ảnh phải. Người duyệt
gán đúng một tag:

- `DUPLICATE_KEEP_LEFT`
- `DUPLICATE_KEEP_RIGHT`
- `DUPLICATE_KEEP_BOTH`
- `NOT_DUPLICATE`

## Tạo bundle offline

Từ thư mục gốc repo:

```powershell
$env:PYTHONUTF8="1"
python scripts/create_cvat_duplicate_review.py `
  --src data/raw `
  --out work/cvat_duplicate_review
```

Kết quả:

```text
work/cvat_duplicate_review/
├── images/                 # contact sheet để đưa vào CVAT
├── duplicate_pairs.csv     # manifest để đối chiếu quyết định
├── duplicate_pairs.json
└── cvat_task_spec.json     # tên task và labels
```

## Tạo task qua CVAT API

Tạo token trong CVAT, sau đó đặt biến môi trường trong phiên PowerShell hiện
tại. Token không commit vào repo:

```powershell
$env:CVAT_URL="http://localhost:8080"
$env:CVAT_TOKEN="<token-cua-anh>"
python scripts/create_cvat_duplicate_review.py `
  --src data/raw `
  --out work/cvat_duplicate_review `
  --upload `
  --task-name "Day09 Duplicate Review"
```

Sau khi review, tải annotation CVAT về và ghép quyết định vào
`duplicate_pairs.csv` bằng `pair_id`/thứ tự frame. Bản mở rộng tiếp theo có thể
thêm lệnh `apply-review` để tự động giữ/xóa ảnh theo các tag đó.
