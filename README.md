# Hệ Thống Đồng Bộ và Quản Lý Dữ liệu Thư Mục Dạng Excel

## Tổng quan

Hệ thống đồng bộ hai chiều thư mục theo dõi chia sẻ SMB/UNC, lưu trữ siêu dữ liệu thư mục vào cơ sở dữ liệu,
và cung cấp giao diện web thời gian thực giống Excel để xem và chỉnh sửa cấu trúc thư mục.

## Bắt đầu nhanh

### Yêu cầu hệ thống
- Python 3.10+
- Node.js 20+
- Docker & Docker Compose (tùy chọn)

### 1. Cấu hình môi trường
```bash
cp .env.example .env
```
Chỉnh sửa file `.env` để thiết lập `SMB_ROOT` (ví dụ: `C:/shared/project` hoặc `\\LOCAL-PC\PROJECT`).

### 2. Khởi chạy Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Tài liệu API: http://localhost:8000/docs

### 3. Khởi chạy Frontend
```bash
cd frontend
npm install
npm run dev
```
Giao diện web: http://localhost:5173

### 4. Chạy với Docker (môi trường sản phẩm)
```bash
docker-compose up -d
```

## Cấu hình

| Biến số        | Mặc định              | Mô tả                            |
|----------------|-----------------------|----------------------------------|
| DATABASE_URL   | sqlite:///./folders.db | Chuỗi kết nối cơ sở dữ liệu     |
| SMB_ROOT       | *(bắt buộc)*          | Đường dẫn thư mục chia sẻ        |
| SCAN_INTERVAL  | 5                     | Khoảng thời gian quét (giây)    |
| SERVER_HOST    | 0.0.0.0               | Host của FastAPI                 |
| SERVER_PORT    | 8000                  | Port của FastAPI                 |
| SMB_USERNAME   | *(tùy chọn)*           | Tên người dùng SMB               |
| SMB_PASSWORD   | *(tùy chọn)*           | Mật khẩu SMB                    |
| EXPORT_DIR     | ./exports             | Thư mục xuất file                |

## Kiến trúc

Xem [ARCHITECTURE.md](ARCHITECTURE.md) để biết thêm thông tin chi tiết về thiết kế hệ thống.

## Giấy phép

MIT