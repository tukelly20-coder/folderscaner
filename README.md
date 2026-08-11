# Hệ Thống Đồng Bộ và Quản Lý Dữ Liệu Thư Mục Dạng Excel

## Tổng quan

Hệ thống này được xây dựng để giải quyết bài toán quản lý hàng ngàn thư mục trong môi trường doanh nghiệp sử dụng chia sẻ mạng SMB/UNC. Trong thực tế, các công ty thường có kho dữ liệu được chia sẻ qua máy chủ Windows với cấu trúc thư mục phức tạp, được thay đổi liên tục bởi nhiều người dùng khác nhau. Việc theo dõi, đặt tên, phân loại và xuất báo cáo thủ công rất dễ xảy ra lỗi, tốn thời gian và không có lịch sử truy xuất.

Dự án cung cấp một giải pháp đồng bộ hai chiều:

- **Tự động phát hiện thay đổi** từ máy tính cục bộ lên SMB Share.
- **Cơ sở dữ liệu trung tâm** lưu trữ toàn bộ trạng thái và lịch sử thư mục.
- **Giao diện Web kiểu Excel** cho phép xem, tìm kiếm, đổi tên và xuất báo cáo theo thời gian thực.

## Kịch bản sử dụng thực tế

### Vấn đề

Một công ty quản lý dự án chia sẻ thư mục `\\SRV-FILES\PROJECTS` chứa hàng nghìn thư mục khách hàng. Nhân viên liên tục tạo, xóa và đổi tên thư mục trực tiếp trong Windows Explorer. Hiện tại:

- Không ai biết ai đã đổi tên thư mục nào và khi nào.
- Cần 1–2 ngày để tổng hợp báo cáo cấu trúc thư mục.
- Việc đổi tên hàng loạt rất dễ nhầm lẫn.
- Không có cơ chế kiểm tra trùng tên trước khi đổi.

### Giải pháp

Với hệ thống này, người quản lý có thể:

- Mở trình duyệt và xem danh sách toàn bộ thư mục giống như bảng Excel.
- Đổi tên trực tiếp trên Web, hệ thống tự động cập nhật lên SMB và ghi lại lịch sử.
- Xuất file Excel chỉ với 1 cú nhấp chuột.
- Theo dõi mọi thay đổi qua mục Lịch sử sự kiện, biết rõ ai đã đổi tên và lúc nào.

## Kiến trúc hệ thống

```
Máy tính người dùng (Windows Explorer)
            │
            ▼
   Chia sẻ mạng SMB/UNC  ─────────────────────────────────────────┐
            │                                                      │
            ▼                                                      │
   Scanner theo dõi (mỗi 5–10 giây)                                │
            │                                                      │
            ▼                                                      │
   Cơ sở dữ liệu (SQLite / PostgreSQL)                            │
            │                                                      │
            ▼                                                      │
   API FastAPI + WebSocket ────────────────────────────────────────┘
            │
            ▼
   Giao diện Web (React + ag-Grid)
```

### Luồng dữ liệu: Từ máy tính lên Web

1. Nhân viên đổi tên hoặc tạo mới thư mục trong Windows Explorer.
2. Scanner phát hiện thay đổi trong chu kỳ quét tiếp theo.
3. Hệ thống xác định loại thay đổi: **Tạo mới / Đổi tên / Xóa / Sửa đổi**.
4. Cập nhật cơ sở dữ liệu và ghi lại sự kiện vào bảng `folder_events`.
5. Thông báo real-time được đẩy đến tất cả các client đang kết nối qua WebSocket.
6. Giao diện Web tự động cập nhật bảng dữ liệu mà không cần người dùng làm mới trang.

### Luồng dữ liệu: Từ Web xuống máy tính

1. Người dùng đổi tên thư mục trực tiếp trên lưới dữ liệu Web.
2. Server xác thực tên hợp lệ (không chứa ký tự cấm, không trùng tên).
3. Server kiểm tra thư mục vẫn tồn tại trên đĩa (tránh xung đột khi người dùng khác đang sửa).
4. Thực hiện đổi tên trên hệ thống tệp SMB.
5. **Chỉ khi thành công**, mới cập nhật cơ sở dữ liệu và thông báo cho các client khác.
6. Nếu thất bại, trả về lỗi và không làm hỏng dữ liệu.

> Nguyên tắc quan trọng: **Hệ thống tệp SMB là nguồn chân lý duy nhất**. Cơ sở dữ liệu chỉ được cập nhật sau khi thay đổi thành công trên đĩa.

## Cấu trúc dự án

```
folderscaner/
├── backend/
│   ├── app/
│   │   ├── api/            # Định tuyến API (folders, events, scanner, websocket, documents)
│   │   ├── config.py       # Cấu hình từ file .env
│   │   ├── database/       # Kết nối cơ sở dữ liệu SQLAlchemy
│   │   ├── main.py         # Điểm vào ứng dụng FastAPI
│   │   ├── models/         # Định nghĩa bảng folders, folder_events, documents
│   │   ├── schemas/        # Pydantic schema cho request/response
│   │   ├── services/       # Logic nghiệp vụ: quét, đổi tên, đồng bộ
│   │   └── websocket/      # Quản lý kết nối WebSocket real-time
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/     # Lịch sử sự kiện, bảng thư mục, trình chỉnh sửa
│   │   ├── pages/          # Trang Dashboard
│   │   ├── services/       # API client, WebSocket client
│   │   └── utils/          # Tiện ích xử lý đường dẫn
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml
├── README.md
└── ARCHITECTURE.md
```

## Tính năng nổi bật và hiệu quả

### 1. Giám sát tự động
Scanner chạy nền với chu kỳ cấu hình (mặc định 5–10 giây). Không cần cài đặt trên từng máy trạm, chỉ cần quyền đọc trên SMB share.

### 2. Đồng bộ hai chiều có kiểm soát
- **Từ đĩa lên Web**: Tự động phát hiện tạo mới, xóa, đổi tên, di chuyển.
- **Từ Web xuống đĩa**: Đổi tên trực tiếp trên Web, hệ thống tự đồng bộ lên SMB.

### 3. Kiểm tra an toàn trước khi đổi tên
- Tên không chứa ký tự cấm của Windows: `< > : " / \ | ? *`
- Không được kết thúc bằng dấu chấm hoặc khoảng trắng.
- Không trùng tên với thư mục cùng cấp.
- Kiểm tra tên dành riêng (CON, PRN, NUL, COM1-9, LPT1-9).
- Xác minh thư mục vẫn tồn tại trên đĩa trước khi đổi (tránh xung đột).

### 4. Lịch sử sự kiện đầy đủ
Mọi thay đổi đều được ghi nhận, bao gồm:
- Thời điểm phát hiện hoặc thực hiện.
- Tên và đường dẫn cũ / mới.
- Nguồn gốc: SCANNER (phát hiện tự động) hoặc WEB (thao tác thủ công).

### 5. Cập nhật real-time
Nhờ WebSocket, tất cả người dùng mở Web đều nhìn thấy thay đổi tức thì mà không cần tải lại trang.

### 6. Giao diện dạng bảng kiểu Excel
- Sắp xếp, lọc, tìm kiếm theo tên và đường dẫn.
- Chỉnh sửa trực tiếp trên ô (inline editing).
- Xuất toàn bộ danh sách ra file Excel (.xlsx) để báo cáo.

### 7. Cấu hình linh hoạt
Các tham số có thể chỉnh sửa qua file `.env`:

| Biến           | Mô tả                                          | Mặc định           |
|----------------|------------------------------------------------|--------------------|
| DATABASE_URL   | Chuỗi kết nối cơ sở dữ liệu                    | sqlite:///./folders.db |
| SMB_ROOT       | Đường dẫn thư mục chia sẻ SMB/UNC               | *(bắt buộc)*       |
| SMB_EXCLUDES   | Danh sách thư mục bỏ qua, phân cách bằng dấu phẩy | sample_folder,test_folder,_deleted |
| SCAN_INTERVAL  | Thời gian quét lại (giây)                       | 10                 |
| SERVER_HOST    | Địa chỉ lắng nghe FastAPI                      | 0.0.0.0            |
| SERVER_PORT    | Cổng FastAPI                                   | 8000               |
| SMB_USERNAME   | Tên đăng nhập SMB (nếu cần xác thực)            | *(để trống)*       |
| SMB_PASSWORD   | Mật khẩu SMB                                    | *(để trống)*       |
| SMB_DOMAIN     | Domain SMB                                      | *(để trống)*       |
| EXPORT_DIR     | Thư mục lưu file xuất Excel                     | ./exports          |

## Công nghệ sử dụng

### Backend
- **Python 3.10+**: Ngôn ngữ xử lý chính.
- **FastAPI**: Framework API hiệu năng cao, tự động tạo tài liệu.
- **SQLAlchemy**: ORM quản lý cơ sở dữ liệu.
- **Pydantic**: Kiểm tra dữ liệu đầu vào / đầu ra.
- **smbprotocol**: Kết nối và truy cập chia sẻ mạng SMB/UNC.
- **pandas + openpyxl**: Xuất báo cáo dạng Excel.

### Frontend
- **React 18**: Giao diện người dùng.
- **TypeScript**: Kiểm tra kiểu dữ liệu.
- **Vite**: Công cụ xây dựng và phát triển nhanh.
- **ag-grid-community**: Bảng dữ liệu năng cao dạng Excel.
- **WebSocket**: Cập nhật thời gian thực.

### Hạ tầng
- **Docker Compose**: Triển khai container backend, frontend và cơ sở dữ liệu.
- **Nginx**: Proxy đảo ngược phục vụ frontend và API trong môi trường sản phẩm.

## Bắt đầu sử dụng

### Yêu cầu
- Python 3.10+
- Node.js 20+
- Docker & Docker Compose (tùy chọn, cho môi trường sản phẩm)

### 1. Cấu hình môi trường

```bash
cp .env.example .env
```

Mở file `.env` và thiết lập `SMB_ROOT` với đường dẫn chia sẻ mạng thực tế, ví dụ:
- `C:/shared/project` (nếu máy chủ là máy cục bộ).
- `\\SRV-FILES\PROJECTS` (nếu truy cập qua mạng).

Nếu chia sẻ yêu cầu xác thực, điền `SMB_USERNAME`, `SMB_PASSWORD` và `SMB_DOMAIN`.

### 2. Khởi chạy Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Tài liệu API tương tác có sẵn tại: http://localhost:8000/docs

### 3. Khởi chạy Frontend

```bash
cd frontend
npm install
npm run dev
```

Giao diện Web chạy tại: http://localhost:5173

### 4. Chạy với Docker

```bash
docker-compose up -d
```

## Xem thêm

Xem file [ARCHITECTURE.md](ARCHITECTURE.md) để hiểu chi tiết về kiến trúc, lược đồ cơ sở dữ liệu và danh sách endpoint API.

## Giấy phép

MIT