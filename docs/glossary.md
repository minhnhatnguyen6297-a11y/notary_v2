# Glossary — Thuật ngữ kỹ thuật dự án notary_v2

Tài liệu này giải thích các thuật ngữ tiếng Anh hay xuất hiện khi làm việc với Claude và Codex.
Mục tiêu: hiểu đủ để thiết kế hệ thống, không cần nhớ định nghĩa học thuật.

Cập nhật: 23/04/2026

---

## Nhóm: Thiết kế hệ thống / Architecture

| Thuật ngữ | Giải thích đơn giản |
|-----------|-------------------|
| **API contract** | "Hợp đồng" giữa backend và frontend — quy định rõ request trông như thế nào, response trả về những field gì. Ai cũng phải tuân theo. Nếu backend tự thêm/xóa field mà không báo thì gọi là *vi phạm contract*. |
| **Contract violation** | Khi code tự ý thêm/bỏ field trong response so với hợp đồng đã thống nhất. Nguy hiểm vì frontend đang parse theo schema cũ sẽ bị vỡ. |
| **Schema** | Bản mô tả cấu trúc dữ liệu — field nào có, kiểu gì, bắt buộc hay không. Ví dụ: schema của `OCRJob` là các cột trong bảng DB. |
| **Endpoint** | Một địa chỉ URL cụ thể trên server để gọi một chức năng. Ví dụ: `POST /api/ocr/analyze` là một endpoint. |
| **Router** | File code chứa các endpoint cùng nhóm. Ví dụ `routers/ocr_ai.py` chứa tất cả endpoint liên quan OCR AI. |
| **Pipeline** | Chuỗi các bước xử lý nối tiếp nhau. OCR pipeline = nhận ảnh → xử lý → trả kết quả. |
| **Payload** | Dữ liệu được gửi kèm trong request hoặc response. Ví dụ: JSON bạn POST lên server là payload. |
| **State machine** | Hệ thống có các *trạng thái* rõ ràng và chỉ chuyển theo đúng luật. Claudex dùng: `awaiting_approval → approved → completed`. Không được nhảy cóc. |
| **Fallback** | Kế hoạch dự phòng khi bước chính thất bại. Ví dụ: QR không đọc được thì *fallback* sang AI OCR. |
| **Invariant** | Quy tắc tuyệt đối không được phá vỡ trong mọi tình huống. Ví dụ: "không được implement trước khi user gõ y" là invariant của Claudex. |

---

## Nhóm: OCR và xử lý ảnh

| Thuật ngữ | Giải thích đơn giản |
|-----------|-------------------|
| **OCR** (Optical Character Recognition) | Công nghệ đọc chữ từ ảnh. Chụp ảnh CCCD → phần mềm nhận ra các ký tự trong ảnh. |
| **Batch** | Xử lý nhiều ảnh cùng lúc, không phải từng ảnh một. "Batch 10 ảnh" = gửi 10 ảnh lên, xử lý và trả về 10 kết quả. |
| **Pairing** | Ghép cặp mặt trước + mặt sau của cùng 1 CCCD từ đống ảnh lộn xộn. Đây là bài toán khó nhất trong OCR pipeline này. |
| **Triage** | Bước phân loại ban đầu: ảnh này là CCCD không? Mặt trước hay sau? Nghiêng hay thẳng? |
| **MRZ** (Machine Readable Zone) | Vùng mã hóa ở mặt sau CCCD, trông như 2 dòng ký tự lạ. Chứa số CCCD, ngày sinh, ngày hết hạn dạng máy đọc được. |
| **QR** | Mã vuông trên CCCD mới. Quét được → có ngay toàn bộ thông tin, chính xác hơn OCR chữ. |
| **Confidence score** | Điểm tin cậy của kết quả OCR, từ 0 đến 1. Score cao = OCR chắc chắn đọc đúng. Score thấp = cần kiểm tra lại. |
| **ROI** (Region of Interest) | Vùng ảnh cần quan tâm. Thay vì OCR toàn bộ ảnh, chỉ cắt đúng vùng chứa số CCCD để tăng tốc và độ chính xác. |
| **Preprocessing** | Xử lý ảnh trước khi đưa vào OCR: tăng độ tương phản, xoay thẳng, khử nhiễu. Giúp OCR đọc chính xác hơn. |
| **Normalization** | Chuẩn hóa kết quả — ví dụ: "10/07/2023" và "10-07-2023" đều ra cùng 1 định dạng chuẩn. |
| **False positive** | Nhận nhầm — ảnh không phải CCCD nhưng hệ thống lại nhận diện là CCCD. Nguy hiểm hơn false negative. |
| **Recall** | Tỷ lệ tìm được đúng trong tổng số đúng thực tế. Recall 90% = trong 10 CCCD thật, hệ thống nhận ra được 9 cái. |
| **Deterministic merge** | Ghép kết quả theo luật cố định, không ngẫu nhiên. Cùng input → luôn ra cùng output. Dễ debug hơn. |

---

## Nhóm: Code và lập trình

| Thuật ngữ | Giải thích đơn giản |
|-----------|-------------------|
| **Scope** | Phạm vi của task — những gì được phép làm. "Out of scope" = không được làm, dù muốn. |
| **Scope violation** | Khi code sửa nhiều hơn phạm vi đã đồng ý. Ví dụ: task chỉ fix bug nhỏ nhưng Codex tự ý refactor thêm 5 file. |
| **Regression** | Lỗi mới xuất hiện do thay đổi code, phá hỏng tính năng đang chạy tốt trước đó. |
| **Regression test** | Test được viết để đảm bảo bug cũ không quay lại. Chạy sau mỗi lần sửa code. |
| **Refactor** | Viết lại code cho sạch hơn mà không thay đổi hành vi. Giống sắp xếp lại bàn làm việc — mọi thứ vẫn ở đó, chỉ gọn hơn. |
| **Debug log / Logging** | Dòng code in thông tin ra để debug. Nguy hiểm nếu để lại trong production vì có thể in ra thông tin nhạy cảm (PII). |
| **PII** (Personally Identifiable Information) | Thông tin cá nhân có thể định danh người dùng: số CCCD, địa chỉ, ngày sinh. Không được log ra hay để lộ. |
| **Migration** | Cập nhật cấu trúc database (thêm cột, đổi tên bảng...) mà không mất dữ liệu cũ. |
| **Latency** | Thời gian chờ từ lúc gửi request đến lúc nhận response. Latency thấp = phản hồi nhanh. |
| **Deadlock** | Tình trạng hai bên đều chờ nhau, không ai tiến được. Ví dụ: A chờ B ghi xong, B chờ A đọc xong → kẹt mãi. |
| **Streaming** | Trả dữ liệu từng phần ngay khi có, không chờ xử lý xong hết. Giống đọc sách từng trang thay vì đợi in xong cả quyển. |
| **Stdout / Stderr** | Stdout = kênh output bình thường của chương trình. Stderr = kênh in lỗi. Hai kênh tách biệt để dễ lọc log. |

---

## Nhóm: Git và quản lý code

| Thuật ngữ | Giải thích đơn giản |
|-----------|-------------------|
| **Commit** | Lưu một mốc thay đổi vào lịch sử git. Giống chụp ảnh trạng thái code tại một thời điểm. |
| **Push** | Đẩy commit từ máy local lên server (GitHub). Người khác mới thấy được. |
| **Pull** | Lấy code mới nhất từ server về máy local. |
| **Branch** | Nhánh code độc lập để phát triển tính năng mới mà không ảnh hưởng code chính. |
| **Worktree** | Thư mục làm việc riêng biệt cho mỗi branch, không cần checkout qua lại. Claude Code dùng để chạy nhiều task song song. |
| **Diff** | Sự khác biệt giữa 2 phiên bản code — dòng nào thêm, dòng nào xóa. |
| **Staged** | File đã được đánh dấu để commit, nhưng chưa commit. |

---

## Nhóm: Claudex / AI workflow

| Thuật ngữ | Giải thích đơn giản |
|-----------|-------------------|
| **Planner** | Vai trò đọc task và lên kế hoạch chi tiết. Không được viết code. |
| **Critic** | Vai trò đọc plan và tìm lỗ hổng, rủi ro. Đối trọng với Planner để tránh plan một chiều. |
| **Finalizer** | Tổng hợp plan gốc + phê bình của Critic thành Final Plan. |
| **Executor** | Vai trò implement code theo Final Plan đã duyệt. |
| **Reviewer** | Sau khi implement xong, đọc lại kết quả và tìm bug, scope violation. |
| **Debate** | Quá trình Planner → Critic → Finalizer tranh luận để ra plan tốt nhất trước khi code. |
| **Artifact** | File kết quả được tạo ra trong quá trình chạy: `planner.md`, `critic.md`, `final_plan.md`... |
| **Run dir** | Thư mục chứa toàn bộ artifact của 1 lần chạy Claudex. Ví dụ: `runtime/codex_relay/20260422-135359-...` |
| **Approval gate** | Điểm dừng bắt buộc — phải có người duyệt (gõ `y`) trước khi tiếp tục. Tránh AI tự ý làm. |
| **Relay** | Chuyển giao task từ Claude sang Codex kèm đầy đủ ngữ cảnh để Codex implement đúng. |
| **Prompt** | Đoạn văn bản ra lệnh/hướng dẫn cho AI. Chất lượng prompt quyết định chất lượng output. |
| **Token** | Đơn vị xử lý của AI — xấp xỉ 1 từ tiếng Anh hoặc 1-2 ký tự tiếng Việt. Dùng để tính chi phí và giới hạn độ dài. |
| **JSONL** | Định dạng file mỗi dòng là 1 JSON độc lập. Dùng để log event stream của Codex theo thời gian thực. |

---

## Nhóm: Vận hành hệ thống

| Thuật ngữ | Giải thích đơn giản |
|-----------|-------------------|
| **Worker** | Tiến trình chạy nền để xử lý task nặng (như OCR) mà không làm chậm web server. Dự án dùng Celery worker. |
| **Queue** | Hàng đợi task. Khi có nhiều ảnh cần OCR, các task xếp vào queue và worker xử lý lần lượt. |
| **Async** | Bất đồng bộ — gửi task rồi không chờ, làm việc khác, khi nào xong thì nhận kết quả. Ngược với sync = chờ đến khi xong. |
| **Poll** | Hỏi đi hỏi lại định kỳ "xong chưa?". Frontend poll status OCR mỗi vài giây để biết khi nào có kết quả. |
| **Warmup** | Khởi động trước khi nhận request thật — load model OCR vào RAM ngay lúc server start để lần gọi đầu không bị chậm. |
| **Benchmark** | Đo hiệu suất có số liệu cụ thể: tốc độ, độ chính xác trên bộ ảnh chuẩn. Dùng để so sánh trước/sau khi thay đổi. |
| **Blast radius** | Mức độ ảnh hưởng nếu thay đổi gây lỗi — thay đổi 1 file nhỏ thì blast radius nhỏ, thay đổi core pipeline thì blast radius lớn. |
