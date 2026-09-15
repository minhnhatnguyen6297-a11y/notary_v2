# Feature specification: Zalo Document Inbox

> **Status:** APPROVED
> **Owner/approver:** User
> **Input:** Nhận text và tài liệu hỗ trợ từ Zalo cá nhân, cho người dùng chọn media và xử lý thành dữ liệu hoặc tài liệu sử dụng ngay
> **Parent source:** `docs/platform/document-intake/spec.md`
> **Created:** 2026-07-30
> **Updated:** 2026-08-07

Tài liệu này định nghĩa **hệ thống phải làm gì** và **vì sao**. Chi tiết triển khai thuộc kế hoạch kỹ thuật sau khi đặc tả được duyệt.

## 1. Goal

- Current problem: Người dùng đang tải ảnh Zalo thủ công, xử lý bằng CamScanner, mở PDF để lấy text, rồi nhập lại dữ liệu vào Excel.
- Expected outcome: Text/media mới từ source bật xuất hiện gần thời gian thực theo hội thoại; user có thể chạy Data Sync 7 ngày dạng best-effort khi cần, rồi chủ động tạo lô media và chọn đầu ra JSON, Excel hoặc PDF.
- User/actor: Nhân viên nghiệp vụ công chứng sử dụng ứng dụng `notary_v2`.

## 2. Scope

### In scope

- Nhận dữ liệu từ tài khoản Zalo cá nhân thông qua connector đã được đăng nhập, duy trì phiên và được user xác nhận intake.
- Source Sync tự discovery và chỉ đồng bộ metadata của friends, groups, strangers và `My Documents` (tên cũ `Zalo Cloud`); cấu hình bật/tắt được lưu theo connector account.
- Friends/groups hiện có và mới mặc định `BẬT`; stranger chưa kết bạn mặc định `TẮT`; `My Documents` là nguồn riêng mặc định `BẬT`.
- Listener realtime luôn nhận event mới khi connected và chỉ lưu text hoặc tải JPG/JPEG/PNG/PDF từ nguồn đang `BẬT`. Self-event chỉ thuộc `My Documents` khi `threadId == session send2me_id`.
- Data Sync chỉ chạy khi user bấm `Đồng bộ dữ liệu`; dùng lịch sử User+Group theo khả năng Zalo trả về, lọc cục bộ tối đa 7 ngày và không cam kết đầy đủ.
- Sau persisted intake consent, tự nhận mọi media hỗ trợ mà connector tải từ source đang `BẬT` vào storage phía backend/server, kể cả media trùng, để người dùng tự quyết định; không tự ghi file vào folder trên máy người dùng.
- Text chỉ là dữ liệu research để sau này thử nghiệm phân loại bằng LLM local; phiên bản này chưa tự phân loại, suy luận nghiệp vụ, xuất text hoặc thực hiện hành động từ text. Zalo Document Inbox chỉ tham chiếu file media gốc do connector quản lý, không ghi đè hoặc tự xóa.
- Cho phép bắt đầu chế độ tạo lô, chuyển qua nhiều hội thoại để chọn ảnh, giữ nguyên lựa chọn khi đổi hội thoại, rồi xử lý toàn bộ ảnh đã chọn.
- Chỉ crop, giảm nhiễu nền, tăng tương phản hoặc resize sau khi người dùng chọn ảnh và chủ động yêu cầu xử lý.
- Backend parser/regex hỗ trợ trích dữ liệu cho ba nhóm giấy tờ trong giai đoạn đầu: CCCD, sổ đỏ và giấy khai tử; giao diện không yêu cầu phân loại ảnh trước OCR.
- Dùng modal và API Cloud AI OCR hiện có để nhận raw OCR text/payload, sau đó backend parser/regex tạo dữ liệu theo contract và người dùng kiểm tra trước khi dữ liệu đi tiếp.
- Cung cấp ba lựa chọn đầu ra: JSON theo contract của `notary_v2`, Excel để sử dụng độc lập và PDF gộp từ ảnh đã chọn.
- Hiển thị trạng thái kết nối Zalo và trạng thái xử lý; lỗi ở bước chuẩn bị, OCR và export có thể thử lại từ UI.

### Out of scope

- Zalo Official Account.
- Dùng wrapper CLI/CRM đa chức năng hoặc fork nguyên upstream làm runtime; connector chỉ dùng trực tiếp dependency `zca-js` đã pin và chỉ có phạm vi nhận dữ liệu.
- CRM, quản lý liên hệ, marketing hoặc tự động gửi tin nhắn Zalo.
- User/auth, phân công nhân viên, claim công việc hoặc tổ chức nhiều đội nhóm.
- Tự động đưa kết quả OCR vào Stage, Pool, Diagram hoặc hồ sơ khi chưa có hành động xác nhận của người dùng.
- Local OCR và QR OCR.
- Tự động sinh Word/hợp đồng trong module này; dữ liệu JSON có thể được luồng `notary_v2` hiện có sử dụng sau đó.
- Trình chỉnh crop thủ công bằng cách kéo bốn góc hoặc bo góc tài liệu.
- SSE/WebSocket browser-facing để đẩy Inbox/UI ở phiên bản đầu; polling UI 2 giây chỉ đọc backend và không thay thế Zalo realtime listener.
- Lưu bền vững, khôi phục hoặc quản lý đồng thời nhiều lô đang chọn trước khi user bấm `Xử lý`.
- Tự động đồng bộ lịch sử khi onboarding, login/session restore hoặc listener reconnect; không prefetch/cache history ngầm.
- Tự động bù lại event xảy ra trong lúc listener mất kết nối hoặc trước khi event được ghi bền vững; gap recovery chỉ là Data Sync thủ công, có thể giảm thiếu sót nhưng không chứng minh đầy đủ.
- Mobile full-sync/decrypt, browser automation và endpoint `getGroupChatHistory` đang trả 404.
- `My Documents` history trước khi có live spike chứng minh khả năng; realtime `My Documents` cũng phải qua live verification trước khi cam kết production-ready.
- Tự động chạy LLM, phân loại, tóm tắt, action hoặc export từ nội dung chat; đây là research function ở giai đoạn sau.
- Nhận hoặc xử lý video, voice, sticker và mọi media ngoài JPG/JPEG/PNG/PDF.
- Runtime implementation; revision này chỉ chốt behavior/UX và technical contract tối thiểu để kiểm thử sau khi user duyệt.
- Đồng bộ thao tác thu hồi tin nhắn/media; media đã tải tiếp tục theo lifecycle nguồn của connector.
- Tự động chuyển connector sang một tài khoản Zalo khác; phiên bản đầu chỉ hỗ trợ một tài khoản đã bind, việc đổi tài khoản cần quy trình reset/onboard riêng.
- Retry tải media realtime từng attachment bằng lệnh từ UI/backend; connector tự retry download. Data Sync chỉ report media history không tải được và cho phép chạy lại toàn sync an toàn.
- Xây hệ thống user/auth mới; module không tự làm auth mà tuân theo ràng buộc triển khai ở R-026 và dùng access control của platform khi có.

## 3. Terms and rule authority

| ID | Term or rule | Precise meaning | Type | Source/decision |
| --- | --- | --- | --- | --- |
| R-001 | Zalo connector (`zca-js`) | Tiến trình Node receive-only trong cùng repo, dùng trực tiếp dependency `zca-js` đã pin để đăng nhập QR, lưu/khôi phục phiên, nhận sự kiện và tải media từ Zalo cá nhân; không cung cấp chức năng gửi tin, CRM hoặc quản trị Zalo | PRODUCT | User confirmed `zca-js` 2026-07-31 |
| R-002 | Zalo Document Inbox | Module trong `notary_v2` quản lý lô ảnh Zalo, thao tác xử lý và các đầu ra | PRODUCT | User confirmed 2026-07-30 |
| R-003 | Lô xử lý | Tập ảnh do người dùng chủ động chọn từ một hoặc nhiều hội thoại sau khi bấm `Tạo lô`; hệ thống không tự tạo lô | PRODUCT | User confirmed 2026-07-30 |
| R-004 | Cloud AI OCR | Giữ route multipart-file và top-level response contract hiện hành của `notary_v2`; 100% item cần OCR được gửi tới Cloud AI OCR, không dùng QR OCR hoặc Local OCR | PRODUCT | `docs/platform/document-intake/spec.md`; user scope 2026-07-30; pure OCR confirmed 2026-08-04 |
| R-005 | Không auto-stage | Đóng modal OCR bằng `x` không lưu chỉnh sửa chưa xác nhận và không save, clear, reset, flush hoặc auto-stage dữ liệu Stage/Pool/Diagram. Raw OCR và batch đã tạo vẫn được giữ đến khi batch hết hạn để user mở lại modal mà không gọi OCR lại | PRODUCT | `AGENTS.md` project red lines; lifecycle clarified 2026-08-03 |
| R-006 | Ảnh gốc | File do connector tải vào storage của host chạy connector; Zalo Document Inbox chỉ tham chiếu và không ghi đè hoặc tự xóa file này | PRODUCT | Data-safety requirement |
| R-007 | Ảnh xử lý | Bản dẫn xuất dùng cho OCR/PDF; luôn có resize và các bước làm rõ ảnh đã bật, còn crop có thể bật hoặc bỏ cho từng ảnh | PRODUCT | User clarified 2026-07-30 |
| R-008 | User-controlled processing | Intake chỉ lưu raw text và trình bày media theo source policy; không tự loại trùng, crop, tiền xử lý, OCR, phân loại/action từ text hoặc xuất file trước hành động rõ ràng của người dùng | PRODUCT | User confirmed 2026-07-30; text boundary clarified 2026-08-07 |
| R-009 | Không phân loại ảnh | Giao diện không gắn hoặc yêu cầu loại giấy tờ; model chỉ trả raw OCR text/payload, còn backend parser/regex tự nhận diện và tạo JSON theo field contract. MVP không dùng model-generated normalized JSON và không triển khai kiến trúc lai | PRODUCT | User confirmed 2026-07-30; architecture confirmed 2026-08-04 |
| R-010 | Trang đầu vào | Một ảnh đầu vào hoặc một trang được tách từ PDF sau khi bấm `Xử lý` là đơn vị nhỏ nhất trong pipeline; cùng một media/trang chỉ xuất hiện một lần trong lô | PRODUCT | User confirmed 2026-07-30/31; duplicate selection clarified 2026-08-03 |
| R-011 | PDF thành ảnh | Khi user bấm `Xử lý`, PDF được thay ngay tại vị trí của nó bằng các trang theo thứ tự; `[A, PDF, B]` trở thành `[A, P1, P2, ..., B]`, rồi từng trang được xử lý như ảnh thông thường | PRODUCT | User confirmed 2026-07-30; ordering clarified 2026-08-03 |
| R-012 | Rectangular crop | Khi user xử lý, hệ thống đề xuất bản crop hình chữ nhật; user chỉ chọn `Có crop` hoặc `Không crop`, không chỉnh bốn góc thủ công | PRODUCT | User confirmed 2026-07-30 |
| R-013 | Không crop | Giữ toàn bộ khung hình trên bản dẫn xuất nhưng vẫn resize, khử nhiễu và tăng tương phản; không có nghĩa là gửi file gốc chưa xử lý vào OCR | PRODUCT | User clarified 2026-07-30 |
| R-014 | Ánh xạ giấy khai tử | Giấy khai tử dùng chung contract `person`, không tạo schema riêng; giá trị đặc thù duy nhất là `ngay_chet`. Số trích lục → `so_giay_to`; ngày ký giấy tờ khai tử → `ngay_cap`; cơ quan đăng ký/cấp → `noi_cap`; nơi chết → `dia_chi` | PRODUCT | User confirmed 2026-07-30 |
| R-015 | Ngày không sử dụng | Không lấy ngày đăng ký khai tử; `ngay_cap` phải là ngày ký giấy tờ khai tử | PRODUCT | User confirmed 2026-07-30 |
| R-016 | Batch retention | Sau khi validation `Xử lý` thành công, backend đặt một `created_at` và `expires_at = created_at + 72 giờ` cho toàn batch. Preview state, working copy, raw/normalized OCR và output dùng chung mốc này; quá hạn thì dữ liệu nội dung bị xóa, không xác nhận/retry/download và job hoàn tất muộn không được publish. Chỉ tombstone không nội dung (`batch_id`, status, expiry) được giữ để URL báo `Hết hạn`. Media nguồn và dữ liệu đã chuyển vào luồng chính dùng lifecycle riêng | PRODUCT | User clarified 2026-07-30; lifecycle unified 2026-08-03 |
| R-017 | Source ownership | Media Zalo gốc do connector quản lý; Zalo Document Inbox không tự xóa file nguồn của connector | PRODUCT | Module boundary confirmed 2026-07-30 |
| R-018 | Local và deployed | Folder trên máy chỉ là cách lưu của môi trường phát triển khi backend chạy local. Khi deploy, connector và `notary_v2` dùng storage phía server; browser chỉ nhận nội dung qua UI/API và không được yêu cầu truy cập đường dẫn local | PRODUCT | User clarified 2026-07-30 |
| R-019 | Webhook, heartbeat, UI polling và QR login | Connector gửi state-change và heartbeat mặc định mỗi 15 giây kèm listener generation; chu kỳ này không phải source reconciliation và backend dùng thời điểm nhận phía server. Ba trạng thái loại trừ nhau, xét theo thứ tự ưu tiên: `Cần đăng nhập lại` khi connector báo session Zalo không dùng được (hết hạn, bị đá, chưa onboard) — trạng thái này thắng mọi trạng thái khác kể cả khi heartbeat cũng ngừng; `Mất kết nối` khi không có heartbeat hợp lệ quá 45 giây mà không có báo cáo session; `Đã kết nối` khi heartbeat trong ngưỡng và session dùng được. Chỉ QR login thành công mới thoát `Cần đăng nhập lại`; heartbeat của generation cũ không đảo được trạng thái của generation mới. Khi mở module, UI chỉ hiển thị nút `Đăng nhập Zalo`, không tự mở QR. Sau khi user bấm nút, hệ thống xóa QR cũ, tạo và hiển thị QR mới cùng thời điểm hết hạn; QR có hiệu lực 100 giây theo connector. Khi QR hết hạn, connector tự xóa QR cũ và yêu cầu mã mới; UI hiển thị mã mới nếu connector còn hoạt động, nếu không thì hiển thị lỗi và nút thử lại. QR quá hạn hoặc QR của phiên cũ không được trả lại cho browser. Tab Inbox visible polling mặc định mỗi 2 giây và refresh ngay khi visible/focus trở lại. Các khoảng thời gian được cấu hình nếu không thuộc giới hạn của connector; chưa dùng SSE/WebSocket | PRODUCT | User approved QR lifecycle 2026-08-05; state machine finalized 2026-08-03 |
| R-020 | Vòng đời lô | Trước `Xử lý`, lựa chọn chỉ nằm trong bộ nhớ trang và có thể mất khi reload/đóng trang. `Xử lý` chỉ tạo batch sau validation toàn lô; backend cấp opaque `batch_id`, tạo working copy/preview state và dùng URL batch đến hết hạn. Inbox chỉ có một link `Lô gần nhất`; tạo lô mới khi lô cũ chưa hoàn tất phải cảnh báo kèm link lô cũ để user mở/lưu trước khi tiếp tục. Không có danh sách, lịch sử, màn hình quản lý lô hoặc hard-cancel job | PRODUCT | User confirmed 2026-07-31; lifecycle finalized 2026-08-03 |
| R-021 | Chuẩn bị preview | Backend sở hữu bước tách PDF và tiền xử lý sau khi batch được tạo. Bước này dùng `Đang chuẩn bị`, `Chờ duyệt`, `Lỗi`, `Hết hạn`; item lỗi có `Thử lại` hoặc `Bỏ`. Batch chỉ vào `Chờ duyệt` khi mọi item còn lại đã chuẩn bị xong; còn item `Đang chuẩn bị` hoặc `Lỗi` thì không cho chọn output, user phải retry hoặc bỏ item đó trước. Khi `Chờ duyệt`, user có thể crop/no-crop, bỏ hoặc đổi thứ tự; reload phải khôi phục state | PRODUCT | User approved preprocessing 2026-07-31; gate finalized 2026-08-03 |
| R-022 | Chốt preview, output và OCR gate | Khi user chọn một hoặc nhiều output và backend ACK, danh sách/thứ tự/crop hiện tại được đóng băng thành một preview snapshot; từ đó browser đóng không hủy job và preview không còn sửa được. PDF dùng snapshot, không gọi model. JSON/Excel dùng chung một OCR result và một OCR gate; result area có một hành động `Xem và xác nhận`, còn từng file được tạo sau xác nhận | PRODUCT | User approved output flow 2026-07-31; ownership finalized 2026-08-03 |
| R-023 | Webhook retry | Connector giữ event/media trong outbox bền vững và retry đến khi `notary_v2` ACK. QR re-login chỉ tạm dừng nhận event mới; delivery worker vẫn gửi event/media đã tải | PRODUCT | User approved target 2026-07-31; re-login clarified 2026-08-03 |
| R-024 | Connector identity và idempotency | `notary_v2` cấp UUID `connector_account_id` khi onboard và connector lưu độc lập với cookie/session. Quét lại QR cùng tài khoản không đổi ID; tài khoản khác bị từ chối cho tới khi reset/onboard riêng. Một message envelope dùng `(connector_account_id, conversation_id, msg_id)`; text của message là thành phần duy nhất trong envelope và từng attachment dùng thêm `attachment_index`. Retry có cùng thành phần/payload trả bản ghi cũ; payload xung đột của chính thành phần đó bị từ chối, không overwrite. Message có cả text và attachments là hợp lệ, không phải conflict; không dedupe theo hash nội dung | PRODUCT | User approved no content dedupe 2026-07-31; lifecycle finalized 2026-08-03; mixed-content clarified by review |
| R-025 | Retry theo bước | Mỗi trang có opaque `input_item_id`. OCR retry chỉ gọi model cho item lỗi, sau đó backend chạy lại parse/pair/shape cho toàn snapshot bằng raw OCR cache của mọi item để kết quả batch nhất quán. Nếu OCR thành công nhưng parse/pair/shape lỗi thì OCR gate ở `Lỗi` với `Thử lại` chỉ chạy lại parse/pair/shape từ raw cache, không gọi model. Mở lại modal không OCR lại. Export retry chỉ tạo lại file từ dữ liệu đã xác nhận. Retry chỉ dừng lại ở các lỗi có thể khắc phục: lỗi tất định như Excel rỗng không có `Thử lại`. Không giới hạn retry thủ công trong phiên bản đầu | PRODUCT | User approved 2026-07-31; parse retry and terminal errors finalized 2026-08-03 |
| R-026 | Biên bảo mật và điều kiện triển khai | Webhook phải được xác thực và bind với đúng `connector_account_id`; session/cookie Zalo chỉ ở connector. `notary_v2` hiện chưa có user authentication/authorization, nên module này MUST chỉ chạy trên máy local hoặc mạng nội bộ tin cậy; MUST NOT expose ra Internet công khai cho tới khi platform có access control. Khi platform bổ sung auth, mọi trang/API thiết lập nguồn, Inbox, batch, preview và download MUST đi qua cơ chế đó; opaque ID không bao giờ thay thế authorization. Production log chỉ dùng opaque/redacted value và không chứa nội dung giấy tờ hoặc định danh Zalo thô | PRODUCT | User approved security target 2026-07-31; deployment constraint corrected 2026-08-03 sau khi xác nhận `main.py` chưa có auth |
| R-027 | OCR API compatibility và ownership | Sau khi output selection được backend ACK, backend sở hữu job và gọi Cloud AI OCR bằng multipart `files` contract của `POST /api/ocr/analyze`; modal trong ngữ cảnh Inbox chỉ review kết quả cache. Multipart filename dùng opaque `input_item_id`, không dùng tên nguồn. Top-level response contract không đổi; production logging của Inbox phải redact `filename`, `before`, `after` và field value | PRODUCT | User requested modal/API reuse; finalized 2026-08-03 |
| R-028 | OCR result review | Trong ngữ cảnh Inbox, modal hiển thị preview, raw OCR text và field đã parse cho phép sửa; `Xác nhận` trả dữ liệu đã sửa về module để xuất JSON/Excel nhưng không ghi Stage/Pool/Diagram. PDF không cần OCR review | PRODUCT | User-approved review principle + existing modal behavior |
| R-029 | `media_object_key` | Khóa object opaque nằm trong namespace của đúng `connector_account_id`; không phải filesystem path/URL/browser value. Connector chỉ gửi webhook sau khi object bất biến đã publish xong; backend chỉ ACK media sau khi key resolve được trong storage cho phép và size/type thực khớp metadata | PRODUCT | Security boundary finalized 2026-08-03 |
| R-030 | Trạng thái kết quả | Chuẩn bị preview dùng R-021. OCR gate dùng `Đang OCR`, `Lỗi`, `Chờ xác nhận`, `Đã xác nhận`, `Hết hạn`. Mỗi output dùng `Đang tạo`, `Sẵn sàng`, `Lỗi`, `Hết hạn`; PDF có thể sẵn sàng trước. Sau `Sẵn sàng`, user chỉ xem dữ liệu đã xác nhận, không sửa hoặc thêm output; muốn thay đổi phải tạo lô mới | PRODUCT | User-approved minimal state model 2026-08-03 |
| R-031 | `input_item_id` và provenance | Opaque ID ổn định cho mỗi ảnh hoặc trang PDF trong snapshot. ID được dùng làm multipart filename, khóa raw OCR cache và `source_refs`; không chứa tên file, tên hội thoại hoặc dữ liệu giấy tờ | PRODUCT | Traceability and retry requirement finalized 2026-08-03 |
| R-032 | Intake consent và source policy | Chỉ sau persisted intake consent, friends/groups hiện có và mới mặc định `BẬT`, strangers chưa kết bạn mặc định `TẮT`, còn `My Documents` mặc định `BẬT`. Khi account chuyển từ policy cũ sang revision này, lần re-consent đầu tiên áp default mới cho toàn inventory hiện có vì dữ liệu cũ không phân biệt default với user choice; từ sau re-consent, mọi toggle user thực hiện được ghi là explicit. Toggle explicit được lưu theo `connector_account_id`; refresh, reconciliation, restart, re-login hoặc reclassification không ghi đè. Nguồn chưa có toggle explicit dùng default theo loại hiện tại | PRODUCT | User-approved design 2026-08-07; legacy migration clarified by review |
| R-033 | Source Sync | Luồng chỉ đồng bộ metadata nguồn, không lấy history, text hoặc media. Tự chạy khi login/session restore, `friend_event`/`group_event`, listener reconnect, targeted lookup cho unknown thread và reconciliation mỗi 60 phút; user có nút `Làm mới nguồn` | PRODUCT | User-approved design 2026-08-07 |
| R-034 | Realtime intake và unknown source | Listener luôn nhận mọi event mới do Zalo giao khi connected, không subscribe/unsubscribe theo toggle; source policy chỉ quyết định bước lưu content/tải media sau khi nhận. Chỉ source `BẬT` mới lưu text hoặc tải JPG/JPEG/PNG/PDF. Unknown friend/group phải được source-resolve rồi xử lý chính event; unknown stranger chỉ tạo metadata tối thiểu ở `TẮT`, không lưu text hoặc tải media. Nếu stranger trở thành friend thì reclassify và dùng friend default chỉ khi chưa có explicit user choice. Realtime có ưu tiên xử lý hơn Data Sync | PRODUCT | User-approved design 2026-08-07 |
| R-035 | `My Documents` | Nguồn riêng có tên hiện tại `My Documents` (tên cũ `Zalo Cloud`), không phải quy tắc cho mọi outgoing self-message. Chỉ nhận self-event khi `threadId == session send2me_id`. Realtime phải được live verification; history chưa được chứng minh và không được cam kết trước live spike | PRODUCT | User-approved design 2026-08-07 |
| R-036 | Data Sync thủ công | Chỉ bắt đầu khi user đã consent và bấm `Đồng bộ dữ liệu` trong lúc listener connected; không prefetch/cache history ngầm. Mỗi connector account chỉ có một run active. Tại lúc bấm, run chốt `cutoff_at` và snapshot ID của source `BẬT` đã ACK, không có policy `Đang áp dụng`, loại `My Documents` cho tới khi live spike history được duyệt. Connector gửi đúng một `requestOldMessages(User)` và một `requestOldMessages(Group)` ở phạm vi thread-type toàn account, rồi lọc response theo snapshot và `sent_at` tối đa 7 ngày. Kết quả là best-effort, có thể thiếu, dùng cùng idempotency key với realtime và user chạy lại an toàn | PRODUCT | User-approved design 2026-08-07; upstream semantics clarified by review |
| R-037 | Chat text research data | Lưu raw text cùng provenance/idempotency tối thiểu. Text không vào production log, LLM, classification, action, notification hoặc export. Text có quota/retention độc lập; áp lực text không dừng media | PRODUCT | User-approved design 2026-08-07 |
| R-038 | Listener coverage gap | Ba trạng thái chính vẫn là `Cần đăng nhập lại`, `Mất kết nối`, `Đã kết nối`; `Đang tự kết nối lại` và `Connector đã dừng` chỉ là lý do của `Mất kết nối`. Event ngoài khoảng listener connected có thể thiếu. Chỉ Data Sync thủ công được dùng để giảm gap; không tự chạy khi onboarding/reconnect và không chứng minh completeness. Event đã vào outbox vẫn retry đến ACK | PRODUCT | User-approved design 2026-08-07 |
| R-039 | Source load và polling boundary | Tải xử lý source tăng theo event volume, không giả định danh sách tĩnh khoảng 1.000 nguồn. Reconciliation source không poll Zalo mỗi 15 giây; chu kỳ 15 giây hiện có chỉ dành cho backend policy/config propagation, tách biệt với reconciliation source mỗi 60 phút | PRODUCT | User-approved design 2026-08-07 |

## 4. User scenarios and acceptance

### US-001: Quản lý nguồn, realtime và Data Sync (Priority: P1)

1. **Given** connector chưa có session Zalo dùng được, **When** user mở khu vực thiết lập nguồn, **Then** khu vực này hiển thị trạng thái chính `Cần đăng nhập lại` và nút `Đăng nhập Zalo`, chưa tự mở mã QR.
2. **Given** user bấm `Đăng nhập Zalo`, **When** connector bắt đầu phiên QR, **Then** hệ thống xóa QR cũ, hiển thị QR mới cùng thời điểm hết hạn và QR có hiệu lực 100 giây.
3. **Given** QR đang hiển thị hết hạn, **When** connector còn hoạt động, **Then** hệ thống xóa QR cũ, tự tạo QR mới và UI hiển thị QR mới mà user không cần reload hoặc bấm refresh.
4. **Given** QR hết hạn hoặc connector dừng, **When** UI polling trạng thái, **Then** QR cũ không còn hiển thị; UI báo lỗi an toàn và có nút `Thử lại`.
5. **Given** user chưa xác nhận intake, **When** connector login hoặc khôi phục session, **Then** Source Sync có thể lập danh mục metadata nhưng Inbox chưa lưu text hoặc tải media; UI nêu rõ default theo từng loại nguồn và yêu cầu persisted consent.
6. **Given** user xác nhận intake lần đầu theo policy mới, **When** account chưa có mốc policy này, **Then** hệ thống áp default mới cho toàn inventory hiện có, không suy đoán trạng thái legacy thiếu provenance là lựa chọn explicit; content intake chỉ được báo sẵn sàng sau khi connector xác nhận đã áp dụng policy.
7. **Given** user đổi một nguồn sang `BẬT` hoặc `TẮT`, **When** connector chưa xác nhận đã áp dụng thay đổi, **Then** UI hiển thị `Đang áp dụng`, content mới của riêng nguồn đó bị fail-closed—không lưu text hoặc tải media theo policy cũ hay mới—và UI không tuyên bố trạng thái mới đã có hiệu lực; sau ACK, lựa chọn được lưu là explicit và login/session restore, refresh, reconnect, reconciliation hoặc reclassification không được ghi đè.
8. **Given** login/session restore, `friend_event`/`group_event`, listener reconnect, chu kỳ 60 phút hoặc user bấm `Làm mới nguồn`, **When** Source Sync chạy, **Then** hệ thống chỉ cập nhật metadata nguồn, không lấy history, text hoặc media.
9. **Given** modal nguồn có nhiều nguồn, **When** danh sách hiển thị, **Then** nguồn có activity được xếp theo activity mới nhất giảm dần, nguồn chưa có activity xếp alphabet và strangers nằm trong khu vực tách rõ.
10. **Given** unknown thread phát sinh event và targeted lookup xác định là friend/group, **When** source được resolve, **Then** source mới mặc định `BẬT` và chính event đang chờ tiếp tục qua realtime intake.
11. **Given** unknown thread phát sinh event và source-resolve xác định là stranger chưa kết bạn, **When** hệ thống xử lý event đầu tiên, **Then** chỉ metadata nguồn tối thiểu được tạo ở `TẮT`; text không được lưu và media không được tải.
12. **Given** một stranger sau đó trở thành friend, **When** Source Sync reclassify source, **Then** source dùng friend default `BẬT` nếu chưa có explicit choice; mọi explicit `BẬT`/`TẮT` trước đó được giữ nguyên.
13. **Given** connector nhận self-event, **When** `threadId == session send2me_id`, **Then** event được xét dưới source riêng `My Documents`; outgoing self-message ở thread khác không được coi là `My Documents`.
14. **Given** `My Documents` đang `BẬT`, **When** realtime listener nhận event matching `send2me_id`, **Then** chỉ xử lý sau khi live verification xác nhận payload/runtime; spec không hứa history của source này trước live spike.
15. **Given** listener `Đã kết nối`, **When** Zalo giao event mới từ source bất kỳ, **Then** listener nhận event không phụ thuộc toggle; source `BẬT` mới được lưu text hoặc tải JPG/JPEG/PNG/PDF với đúng source/thời điểm và cùng khóa idempotency dùng cho Data Sync.
16. **Given** source đang `TẮT` hoặc event là video/voice/sticker/file không hỗ trợ, **When** listener nhận event, **Then** Inbox không lưu content, không tải media và không tạo placeholder; toggle không làm listener unsubscribe source.
17. **Given** cùng một idempotency key được realtime hoặc Data Sync giao lại, **When** backend đã có payload giống hệt, **Then** hệ thống tính là duplicate và không tạo text/media thứ hai; payload xung đột bị từ chối.
18. **Given** connector gửi state-change/heartbeat, **When** UI cập nhật, **Then** chỉ một trạng thái chính được chọn theo ưu tiên `Cần đăng nhập lại` > `Mất kết nối` > `Đã kết nối`; reconnect/stopped chỉ là lý do của `Mất kết nối`.
19. **Given** listener không nhận liên tục, **When** event có thể đã xảy ra ngoài outbox, **Then** UI hiển thị khoảng có thể thiếu; onboarding/reconnect không tự chạy history và không tuyên bố dữ liệu đầy đủ.
20. **Given** chưa consent, connector không ở `Đã kết nối`, account còn policy `Đang áp dụng` hoặc đang có Data Sync active, **When** user xem hành động `Đồng bộ dữ liệu`, **Then** nút bị disabled và không có history nào được prefetch/cache ngầm.
21. **Given** user đã consent, connector `Đã kết nối` và chưa có run active, **When** user bấm `Đồng bộ dữ liệu`, **Then** hệ thống chốt `cutoff_at` cùng snapshot ID source `BẬT` đã ACK tại thời điểm bấm, loại `My Documents` trước live-spike approval và bắt đầu đúng một run cho account.
22. **Given** run đã bắt đầu, **When** connector yêu cầu history, **Then** connector gửi đúng một `requestOldMessages(User)` và một `requestOldMessages(Group)` ở phạm vi thread-type toàn account; response được lọc cục bộ theo source snapshot và cửa sổ tối đa 7 ngày, không gọi history riêng cho từng source.
23. **Given** upstream trả một tập history không có count/window/completeness guarantee, **When** Data Sync xử lý response, **Then** local source snapshot và 7-day cutoff là authoritative, item không đủ điều kiện bị bỏ và UI mô tả kết quả là best-effort, có thể thiếu.
24. **Given** lịch sử đủ điều kiện có text hoặc JPG/JPEG/PNG/PDF còn tải được, **When** Data Sync xử lý, **Then** content được import bằng cùng idempotency key với realtime; URL media hết hạn/không tải được chỉ tăng `media download failures`, không tạo placeholder giả.
25. **Given** Data Sync đang chạy, **When** user xem progress/result, **Then** UI hiển thị trạng thái `Đang đồng bộ` và năm count `received`, `duplicates`, `imported text`, `imported media`, `media download failures`; nút sync vẫn disabled cho tới khi run kết thúc.
26. **Given** run nhận xong hai response và xử lý hết backlog, **When** kết thúc, **Then** trạng thái là `Hoàn tất best-effort`; nếu thiếu response quá timeout cấu hình, request/processing thất bại hoặc listener ngắt giữa run thì trạng thái là `Lỗi`, giữ các item đã ACK/idempotent và user có thể bấm chạy lại sau khi connected.
27. **Given** Data Sync backlog đang xử lý và realtime event mới đến, **When** hai luồng cạnh tranh tài nguyên, **Then** realtime được ưu tiên và không phải chờ toàn bộ history job hoàn tất.
28. **Given** listener gap đã được cảnh báo, **When** user chạy Data Sync, **Then** kết quả có thể giảm gap nhưng cảnh báo không tự xóa và không được suy diễn thành đã khôi phục đầy đủ.
29. **Given** user đổi toggle sau khi một run đã bắt đầu, **When** run tiếp tục, **Then** run giữ nguyên source snapshot đã chốt; lựa chọn mới chỉ áp dụng cho realtime sau policy ACK và Data Sync lần sau.
30. **Given** event đã vào download queue/outbox, **When** backend hoặc Zalo session tạm thời không dùng được, **Then** delivery retry tới khi backend ACK mà không cần listener nhận lại event.

### US-002: Chọn và chuẩn bị ảnh (Priority: P1)

1. **Given** inbox có nhiều ảnh, **When** người dùng bấm `Tạo lô`, **Then** giao diện chuyển sang chế độ chọn ảnh nhưng chưa xử lý ảnh nào.
2. **Given** chế độ tạo lô đang mở, **When** user chuyển nhiều hội thoại và chọn ảnh, **Then** lựa chọn được giữ; chọn lại cùng media không tạo phần tử thứ hai.
3. **Given** Inbox nhận media mới trong lúc chọn lô, **When** polling cập nhật, **Then** media chỉ nối cuối, không reorder item cũ, không auto-scroll và không làm mất lựa chọn.
4. **Given** user chưa bấm `Xử lý`, **When** reload, đóng trang hoặc hủy lô, **Then** lựa chọn hiện tại được phép mất và không cần khôi phục.
5. **Given** lô vượt bất kỳ giới hạn file/trang/byte/pixel, **When** user bấm `Xử lý`, **Then** toàn lô bị từ chối trước khi tạo batch, lựa chọn phía browser vẫn còn và lỗi chỉ rõ giới hạn cần giảm.
6. **Given** validation thành công, **When** backend ACK `Xử lý`, **Then** backend cấp `batch_id`, tạo working copy và chuyển batch sang `Đang chuẩn bị`; đóng trang không hủy bước này.
7. **Given** một item lỗi khi tách PDF hoặc tiền xử lý, **When** preview mở lại, **Then** item hiển thị `Lỗi` với `Thử lại`/`Bỏ`, batch chưa vào `Chờ duyệt` và user chưa chọn được output cho tới khi item đó thành công hoặc bị bỏ.
8. **Given** batch `Chờ duyệt`, **When** preview mở, **Then** user thấy toàn bộ lô, không bị ép duyệt tuần tự; mỗi item có hội thoại/thời điểm, còn trang PDF thêm tên nguồn và `trang n/N`.
9. **Given** user đổi crop/no-crop, bỏ item hoặc đổi thứ tự, **When** reload URL batch trước khi chốt preview, **Then** preview state đã lưu được khôi phục đúng.
10. **Given** hệ thống tạo crop hình chữ nhật, **When** user xem preview, **Then** user có thể chọn `Không crop`; bản toàn khung vẫn resize và làm rõ.
11. **Given** hệ thống không tìm được hình chữ nhật đủ tin cậy, **When** preprocess hoàn tất, **Then** dùng bản toàn khung đã tiền xử lý và báo rõ ảnh chưa crop.
12. **Given** lô có thứ tự `[A, PDF, B]`, **When** PDF được tách trang, **Then** preview ban đầu có thứ tự `[A, P1, P2, ..., B]`.
13. **Given** một nguồn bị tắt sau khi media của nguồn đó đã được chọn, **When** user tiếp tục xử lý, **Then** media đã chọn vẫn hợp lệ; việc tắt chỉ chặn event mới.
14. **Given** user bỏ hết item trong preview, **When** lô không còn item nào, **Then** hệ thống không cho chọn output và chỉ cho quay lại Inbox để tạo lô mới.
15. **Given** preview đang `Chờ duyệt`, **When** user chọn output và backend ACK, **Then** một snapshot bất biến được chốt; mọi OCR/PDF/retry sau đó dùng đúng snapshot và preview không còn sửa được.
16. **Given** một source media không còn đọc được trước `Xử lý`, **When** backend validation, **Then** toàn lô chưa được tạo, item báo `File nguồn không còn` và user phải bỏ item hoặc nhận lại media.

### US-003: Raw OCR và backend parser/regex (Priority: P1)

1. **Given** snapshot đã chốt và JSON và/hoặc Excel được chọn, **When** backend bắt đầu OCR, **Then** OCR gate chuyển `Đang OCR` và backend gửi đúng ảnh snapshot bằng opaque `input_item_id`, không chạy lại crop/denoise/contrast.
2. **Given** backend parser/regex không nhận được một số trường, **When** kết quả được trả về, **Then** hệ thống giữ raw OCR text trong `raw_results`, cảnh báo phần chưa trích được và không yêu cầu user phân loại ảnh.
3. **Given** raw OCR text là giấy khai tử, **When** backend parser/regex tạo bản ghi người, **Then** chỉ thêm `ngay_chet` và ánh xạ các thông tin giấy tờ vào các trường người hiện có theo R-014/R-015.
4. **Given** một item bị lỗi kỹ thuật OCR, **When** các item khác thành công, **Then** OCR gate chuyển `Lỗi`, không tạo JSON/Excel partial; `Thử lại` chỉ OCR item lỗi rồi chạy lại parse/pair/shape toàn snapshot từ raw cache.
5. **Given** mọi item OCR thành công nhưng bước parse/pair/shape lỗi, **When** user bấm `Thử lại` ở OCR gate, **Then** hệ thống chỉ chạy lại parse/pair/shape từ raw cache và không gọi model lần nào.
6. **Given** mọi trang OCR thành công, **When** raw/parsed result sẵn sàng, **Then** result area có đúng một OCR gate `Chờ xác nhận` với hành động `Xem và xác nhận` dùng chung cho JSON/Excel.
7. **Given** modal OCR đang mở, **When** user đóng bằng `x`, **Then** chỉnh sửa chưa xác nhận không được lưu, Stage/Pool/Diagram không đổi, raw OCR vẫn còn và OCR gate tiếp tục `Chờ xác nhận`.
8. **Given** OCR gate đang `Chờ xác nhận`, **When** user mở lại modal, **Then** hệ thống dùng kết quả OCR đã có và không gọi model lần nữa.
9. **Given** user sửa field và bấm `Xác nhận`, **When** dữ liệu được trả về module, **Then** OCR gate chuyển `Đã xác nhận` và JSON/Excel được tạo từ đúng dữ liệu đó; đóng modal hoặc retry export không ghi Stage/Pool/Diagram.
10. **Given** lô được gửi OCR, **When** pipeline chạy, **Then** chỉ Cloud AI OCR được sử dụng và QR/Local OCR không được gọi.
11. **Given** backend đã ACK output selection, **When** user đóng hoặc reload trang trong lúc OCR/export, **Then** job tiếp tục phía backend và URL batch phản ánh trạng thái mới nhất.

### US-004: Ảnh PNG và tài liệu PDF (Priority: P1)

1. **Given** một ảnh PNG được chọn, **When** user bấm `Xử lý`, **Then** hệ thống giữ file PNG gốc và đưa một bản ảnh tương thích vào cùng pipeline như JPG/JPEG.
2. **Given** một PDF nhiều trang được chọn, **When** user bấm `Xử lý`, **Then** toàn bộ trang được chuyển thành ảnh tại đúng vị trí PDF trong lô và xuất hiện trong preview như ảnh thông thường.

### US-005: Chọn đầu ra (Priority: P1)

1. **Given** user chọn một hoặc nhiều output tại preview, **When** backend ACK, **Then** preview và tập output được freeze trong cùng thao tác; selection gửi sau đó bị từ chối kể cả khi mang tập output khác, còn gửi lại đúng selection đã ACK trả về kết quả cũ.
2. **Given** JSON đã được chọn, **When** OCR được xác nhận và export thành công, **Then** JSON `Sẵn sàng` với contract mục 6.1.
3. **Given** Excel đã được chọn và dữ liệu xác nhận có `persons` và/hoặc `properties`, **When** export thành công, **Then** workbook chỉ có sheet `Nguoi` và/hoặc `So_do` có dữ liệu.
4. **Given** Excel đã được chọn nhưng `persons` và `properties` đều rỗng, **When** export chạy, **Then** không tạo workbook và output `Lỗi` với lý do `Không có dữ liệu để xuất Excel`; đây là lỗi tất định nên không có `Thử lại`, user phải tạo lô mới.
5. **Given** PDF đã được chọn, **When** ảnh tiền xử lý sẵn sàng, **Then** PDF được tạo theo thứ tự preview mà không gọi OCR và có thể `Sẵn sàng` trước JSON/Excel.
6. **Given** output đang tạo, thành công, lỗi hoặc quá hạn, **When** user xem URL batch, **Then** từng file hiển thị một trong `Đang tạo`, `Sẵn sàng`, `Lỗi`, `Hết hạn`; file sẵn sàng có nút tải, còn file lỗi chỉ có `Thử lại` khi lỗi có thể khắc phục và không có `Thử lại` khi lỗi tất định.
7. **Given** export lỗi sau khi OCR đã được xác nhận, **When** user bấm `Thử lại`, **Then** chỉ file lỗi được tạo lại từ dữ liệu đã xác nhận, không OCR hoặc xác nhận lại.
8. **Given** user đóng/mất URL batch, **When** mở Inbox trước khi batch hết hạn, **Then** một link `Lô gần nhất` mở được batch gần nhất còn hiệu lực, dù job đang chạy hay đã hoàn tất.
9. **Given** quá 72 giờ từ `created_at` của batch đã validation thành công, **When** user mở batch, **Then** batch và output hiển thị `Hết hạn`, không xác nhận/retry/download được và dữ liệu tạm được cleanup mà không xóa media nguồn.
10. **Given** output đã `Sẵn sàng`, **When** user muốn sửa dữ liệu hoặc thêm output, **Then** phiên bản đầu yêu cầu tạo lô mới; user vẫn mở lại modal để xem dữ liệu đã xác nhận ở chế độ chỉ đọc.
11. **Given** `Lô gần nhất` chưa hoàn tất preparation/preview/OCR/output, **When** user bấm `Tạo lô` mới, **Then** cảnh báo hiển thị link lô cũ để mở/lưu và chỉ tiếp tục sau khi user xác nhận.

### US-006: An toàn dữ liệu (Priority: P1)

1. **Given** ảnh chứa dữ liệu cá nhân, **When** hệ thống ghi log hoặc báo lỗi, **Then** log không chứa cookie/session Zalo hay toàn bộ nội dung giấy tờ.
2. **Given** OCR hoặc xuất file thất bại, **When** người dùng thử lại, **Then** ảnh gốc và kết quả hợp lệ trước đó không bị ghi đè hoặc xóa.
3. **Given** webhook thiếu/sai secret, thiếu field bắt buộc hoặc `media_object_key` nằm ngoài storage cho phép, **When** backend nhận request, **Then** request bị từ chối mà không đọc file hoặc ghi dữ liệu Inbox.
4. **Given** hệ thống ghi production log, **When** log được kiểm tra, **Then** log chỉ có opaque ID/trạng thái/lỗi kỹ thuật tối thiểu và không chứa cookie/session, ảnh, tên file gốc, tên/ID Zalo thô, raw chat text, raw/normalized field value hoặc nội dung giấy tờ.
5. **Given** một media OCR lỗi hoặc một output export lỗi, **When** user bấm thử lại, **Then** hệ thống chỉ chạy lại bước lỗi và giữ nguyên các bước/media đã thành công.
6. **Given** lô chứa file sai loại, vượt giới hạn an toàn hoặc PDF hỏng/có mật khẩu, **When** user bấm `Xử lý`, **Then** toàn lô bị từ chối trước khi tạo batch, hệ thống chỉ rõ item và lý do, lựa chọn phía browser vẫn còn để user bỏ item đó rồi `Xử lý` lại; hệ thống MUST NOT âm thầm xử lý phần còn lại.
7. **Given** download request dùng file ID không hợp lệ/hết hạn, hoặc bỏ qua access control khi platform đã có, **When** backend nhận request, **Then** backend từ chối mà không tiết lộ filesystem path hay xác nhận nội dung file.
8. **Given** platform đã có access control, **When** request tới thiết lập nguồn, Inbox, batch, preview hoặc download không đi qua cơ chế đó, **Then** backend từ chối dù ID có hợp lệ.
9. **Given** webhook có `connector_account_id` đúng format nhưng chữ ký/binding không khớp hoặc cùng idempotency key mang payload khác, **When** backend nhận request, **Then** backend từ chối và không overwrite dữ liệu đã có.
10. **Given** `notary_v2` chưa có user authentication/authorization, **When** module được triển khai, **Then** module chỉ chạy trên máy local hoặc mạng nội bộ tin cậy và không được expose công khai.
11. **Given** connector đạt hard quota media nguồn, **When** media mới đến, **Then** connector dọn media không còn được batch chưa hết hạn tham chiếu trước; nếu vẫn không đủ chỗ thì tạm dừng nhận/publish media mới, hiển thị `Bộ nhớ nhận Zalo đã đầy`, không xóa media được bảo vệ và tự tiếp tục khi có dung lượng.
12. **Given** batch đã bị cleanup sau 72 giờ, **When** user mở file JSON/Excel đã tải trước đó, **Then** các cột/field nguồn vẫn cho biết hội thoại, thời điểm và trang tương ứng.
13. **Given** text đạt retention hoặc text quota, **When** cleanup chạy, **Then** text cũ nhất bị xóa trước; nếu vẫn không đủ chỗ thì chỉ text intake dừng với `Bộ nhớ chat đã đầy`, media intake còn quota vẫn tiếp tục và text tự tiếp tục khi có dung lượng.

## 5. Functional requirements

- **FR-001:** Khu vực thiết lập nguồn MUST là điểm vào duy nhất cho kết nối Zalo. Trước intake đầu tiên, UI MUST nêu rõ friends/groups và `My Documents` mặc định `BẬT`, strangers mặc định `TẮT`, cùng loại content được lưu; chưa có persisted consent thì Source Sync MAY ghi metadata nhưng Inbox MUST NOT lưu text hoặc tải media. Với account có inventory từ policy cũ, lần re-consent đầu tiên MUST áp default mới cho inventory hiện có và tạo mốc policy mới; từ sau mốc đó, mỗi toggle user thực hiện MUST được lưu là explicit theo `connector_account_id`. Explicit choice MUST không bị default, refresh, reconciliation, restart, re-login hoặc reclassification ghi đè; nguồn chưa có explicit choice dùng default theo loại hiện tại. Nếu user tắt mọi nguồn, Inbox MUST có empty state dẫn tới khu vực chọn nguồn.
- **FR-002:** Listener MUST luôn nhận mọi event mới do Zalo giao khi connected; toggle MUST NOT subscribe/unsubscribe listener mà chỉ gate lưu content/tải media sau khi nhận. Với source `BẬT`, connector MUST lưu raw text và tải/chuyển JPG/JPEG/PNG/PDF; với source `TẮT`, MUST không lưu content hoặc tải media. Unknown friend/group MUST được targeted source-resolve, tạo theo friend/group default rồi xử lý chính event đang chờ. Unknown stranger MUST chỉ tạo metadata tối thiểu ở `TẮT`, không lưu text hoặc tải media. Stranger được reclassify thành friend MUST dùng friend default chỉ khi chưa có explicit user choice. Video, voice, sticker và file khác MUST không được lưu, tải, hiển thị hoặc tạo placeholder; media hỗ trợ MUST NOT bị ẩn theo hash nội dung.
- **FR-003:** Hệ thống MUST dùng media nguồn bất biến do connector quản lý, tạo bản dẫn xuất riêng cho tiền xử lý và MUST NOT ghi đè hoặc tự xóa media nguồn.
- **FR-004:** Hệ thống MUST cho phép chọn một hoặc nhiều ảnh từ nhiều hội thoại và đổi thứ tự; cùng một media/trang MUST NOT xuất hiện hai lần trong một lô.
- **FR-005:** Hệ thống MUST chỉ crop, giảm nhiễu, tăng tương phản và resize trên bản dẫn xuất sau hành động xử lý rõ ràng của người dùng.
- **FR-006:** Hệ thống MUST giữ file gốc bất biến, mặc định đề xuất crop hình chữ nhật khi đủ tin cậy, cho phép đổi từng ảnh sang `Không crop` và MUST NOT cung cấp editor kéo bốn góc thủ công.
- **FR-007:** Cloud model MUST chỉ trả raw OCR text/payload; backend parser/regex MUST tự nhận diện và tạo đúng field contract ở mục 6.1 cho CCCD, sổ đỏ và giấy khai tử mà không yêu cầu phân loại ảnh trước OCR. Model-generated normalized JSON MUST NOT được coi là nguồn dữ liệu chuẩn trong MVP; đổi sang hướng đó phải sửa lại spec.
- **FR-008:** 100% item cần OCR MUST dùng Cloud AI OCR hiện có. Active OCR runtime MUST NOT decode QR giấy tờ, dùng QR fallback/priority hoặc gọi Local OCR; quy định này không ảnh hưởng QR dùng để đăng nhập Zalo connector.
- **FR-009:** Hệ thống MUST NOT tự ghi kết quả vào Stage/Pool/Diagram. Đóng modal OCR bằng `x` MUST không lưu chỉnh sửa chưa xác nhận, không clear/reset/flush raw OCR hoặc batch, và không auto-stage.
- **FR-010:** Sau khi duyệt preview, user MUST chọn đúng một lần một hoặc nhiều output JSON, Excel và PDF. PDF không cần OCR; JSON/Excel dùng chung một OCR gate và chỉ tạo file sau một lần `Xác nhận`. Khi JSON hoặc Excel được chọn, result area MUST có đúng một dòng OCR dùng các trạng thái R-030 và hành động `Xem và xác nhận` khi chờ; lô chỉ chọn PDF MUST NOT có dòng OCR. Mỗi output đã chọn MUST có một dòng riêng với trạng thái/file tương ứng.
- **FR-011:** Connector MUST gửi heartbeat mặc định mỗi 15 giây kèm listener generation; chu kỳ này chỉ phục vụ heartbeat/backend allowlist-config propagation, MUST NOT gọi Zalo để reconciliation source; backend dùng thời điểm nhận phía server. Inbox MUST hiển thị đúng một trong ba trạng thái loại trừ nhau theo thứ tự ưu tiên `Cần đăng nhập lại` > `Mất kết nối` > `Đã kết nối`: `Cần đăng nhập lại` khi connector báo session Zalo không dùng được và chỉ thoát khi QR login thành công; `Mất kết nối` khi thiếu heartbeat hợp lệ quá 45 giây mà không có báo cáo session; `Đã kết nối` khi heartbeat trong ngưỡng và session dùng được. Heartbeat generation cũ MUST NOT đảo trạng thái generation mới. Khi vào module, UI MUST chỉ hiển thị nút `Đăng nhập Zalo`, không tự hiển thị hoặc mở QR. Sau khi user bấm nút, backend MUST bỏ QR cũ trước khi khởi động/restart phiên QR; QR mới MUST có `generated_at` và `expires_at`, có hiệu lực 100 giây theo connector. Khi QR hết hạn, connector MUST xóa QR cũ và tự yêu cầu QR mới; nếu connector còn hoạt động UI MUST hiển thị QR mới, nếu không MUST hiển thị lỗi an toàn và nút `Thử lại`. Backend/UI MUST NOT public QR quá hạn hoặc QR còn sót từ phiên cũ. Hai trạng thái lỗi MUST có hành động `Kết nối lại/Quét QR`; các ngưỡng cấu hình được.
- **FR-012:** Vì `notary_v2` chưa có user authentication/authorization, module MUST chỉ được triển khai trên máy local hoặc mạng nội bộ tin cậy và MUST NOT expose công khai. Khi platform có access control, mọi trang/API thiết lập nguồn, Inbox, batch, preview và download MUST dùng cơ chế đó; opaque ID không phải authorization và MUST NOT được coi là biện pháp bảo vệ. Session Zalo không rời connector; production log chỉ dùng opaque/redacted ID và không ghi raw chat text, nội dung giấy tờ, tên nguồn hoặc field value.
- **FR-013:** Hệ thống MUST cho phép một lô chứa mọi ảnh do user chọn, bao gồm ảnh từ nhiều hội thoại, nhiều người và nhiều loại giấy tờ; hệ thống không tự tách lô.
- **FR-014:** Khi crop tự động sai hoặc user không muốn dùng bản crop, hệ thống MUST cho phép chọn `Không crop` bằng một thao tác; ảnh toàn khung vẫn MUST qua resize và các bước tiền xử lý khác trước OCR.
- **FR-015:** PDF đầu ra MUST dùng bản xử lý hiện tại của từng ảnh: crop hoặc toàn khung theo lựa chọn user, sau đó đã resize và áp dụng các bước làm rõ ảnh.
- **FR-016:** Excel MUST có tối đa hai sheet: `Nguoi` và `So_do`, chỉ tạo sheet có dữ liệu và không tạo sheet raw OCR. Nếu `persons` và `properties` đều rỗng, hệ thống MUST không tạo workbook và đặt output `Lỗi` với lý do `Không có dữ liệu để xuất Excel`.
- **FR-017:** Sau khi validation `Xử lý` thành công, backend MUST cấp opaque `batch_id`, đặt `expires_at = created_at + 72 giờ` cho toàn batch và cung cấp URL batch; khi platform có access control, URL này MUST đi qua cơ chế đó. Inbox chỉ hiển thị `Lô gần nhất`; cảnh báo thay lô phải chứa link lô cũ để user mở/lưu. Result area hiển thị `Hết hạn lúc …`; file tải dùng `lo-YYYYMMDD-HHmm-<short-id>.<ext>`. Cleanup MUST không xóa media nguồn hoặc dữ liệu đã chuyển vào luồng chính, và browser MUST không nhận filesystem path.
- **FR-018:** Hệ thống MUST NOT tự gom ảnh theo timer, mention hoặc khoảng im lặng; lô chỉ tồn tại sau khi user bấm `Tạo lô` và chọn ảnh.
- **FR-019:** Giấy khai tử MUST trả một bản ghi trong `persons`, không tạo schema riêng; MUST map số trích lục vào `so_giay_to`, ngày ký giấy tờ khai tử vào `ngay_cap`, cơ quan đăng ký/cấp vào `noi_cap`, nơi chết vào `dia_chi`, thêm giá trị đặc thù `ngay_chet`, và MUST NOT dùng ngày đăng ký khai tử.
- **FR-020:** Khi tab Inbox đang visible, giao diện MUST polling backend mặc định mỗi 2 giây để cập nhật state/data đã ingest; chu kỳ UI này MUST không thay listener realtime hoặc gọi Zalo Source Sync/Data Sync. Khi tab visible/focus trở lại, MUST refresh ngay. Trong lúc chọn lô, media mới chỉ nối cuối, không reorder item cũ, auto-scroll hoặc làm mất lựa chọn; lựa chọn được giữ khi đổi hội thoại đến `Xử lý` hoặc hủy lô.
- **FR-021:** Hệ thống MUST giữ PNG gốc; khi user bấm `Xử lý`, bản dẫn xuất MUST được chuẩn hóa nền/màu và đi qua cùng pipeline ảnh như JPG/JPEG.
- **FR-022:** Khi user bấm `Xử lý`, hệ thống MUST thay mỗi PDF tại đúng vị trí của nó bằng toàn bộ trang ảnh theo thứ tự, rồi cho phép bỏ/đổi thứ tự từng trang trong preview như ảnh thường.
- **FR-023:** Mọi webhook MUST có `schema_version`, `event_type`, `connector_account_id` và chữ ký/thời điểm chống replay bind với connector đó. Message envelope thêm `conversation_id`, `conversation_type`, `source_display_name`, `msg_id`, `sent_at`, optional raw text và zero-or-more attachment gồm `attachment_index`, `media_object_key`, `mime_type`, `size_bytes`; state/heartbeat thêm trạng thái, listener generation và `observed_at`. Realtime và Data Sync MUST dùng component keys R-024 giống nhau. Envelope chỉ ACK sau khi mọi component đủ điều kiện đã được ghi bền vững hoặc là duplicate giống hệt; text và attachment cùng message không xung đột nhau. State/heartbeat ACK sau khi current state được cập nhật. Component payload xung đột, replay, sai secret/key/type/size MUST bị từ chối không overwrite.
- **FR-024:** Giao diện MUST giữ đủ danh sách media và thứ tự trong bộ nhớ khi user chuyển qua nhiều hội thoại trong cùng phiên chọn; hệ thống MUST NOT lưu hoặc khôi phục lô đang chọn trước khi user bấm `Xử lý`.
- **FR-025:** Backend MUST sở hữu `Đang chuẩn bị`/`Chờ duyệt` state, working copy, item order, crop/no-crop và ảnh dẫn xuất. Preview hiển thị toàn lô với source context; item chuẩn bị lỗi có `Thử lại`/`Bỏ`. Khi output selection được ACK, backend MUST freeze snapshot bất biến; reload khôi phục đúng state và không cho sửa snapshot đã freeze.
- **FR-026:** PDF MUST dùng snapshot và không gọi OCR. JSON/Excel dùng một OCR result và một lần xác nhận. Sau backend ACK output selection, job MUST tiếp tục độc lập với tab; mở lại modal hoặc retry export MUST không gọi model lại.
- **FR-027:** `notary_v2` MUST cấp UUID `connector_account_id` khi onboard và connector lưu độc lập với Zalo session; re-login cùng tài khoản giữ ID. Tài khoản khác MUST bị từ chối cho tới quy trình reset ngoài scope. Outbox/delivery đã tải tiếp tục qua re-login; backend không dedupe hash nội dung.
- **FR-028:** Nếu một item lỗi OCR, JSON/Excel MUST không được tạo partial. Retry chỉ OCR item lỗi theo `input_item_id`, rồi MUST chạy lại parse/pair/shape toàn snapshot bằng raw cache mọi item. Export retry chỉ tạo lại file từ dữ liệu đã xác nhận. Không giới hạn retry thủ công; mỗi OCR retry là model call mới cho item lỗi.
- **FR-029:** Trước khi tạo batch, backend MUST kiểm tra toàn bộ lựa chọn và từ chối nguyên tử nếu vượt bất kỳ giới hạn nào: mặc định 20 MB/file và 100 ảnh/trang, cùng giới hạn tổng source bytes và decoded/rendered pixels do deployment cấu hình. Không tự chia lô hoặc âm thầm bỏ item; lỗi giữ lựa chọn browser và chỉ rõ giới hạn. Giá trị tổng byte/pixel được chốt theo tài nguyên deployment trước khi triển khai.
- **FR-030:** Connector MUST không đưa credential vào webhook/browser/log. Browser MUST không nhận filesystem path. Multipart OCR filename dùng opaque `input_item_id`; production log MUST redact `filename`, `source_display_name`, Zalo IDs, `before`/`after`, raw/normalized field value, raw chat text và nội dung giấy tờ.
- **FR-031:** Backend Inbox MUST gọi Cloud AI OCR bằng multipart `files` contract hiện có của `POST /api/ocr/analyze`; modal Inbox chỉ review cached result. Endpoint không nhận `media_id`, không đổi top-level keys và không chạy lại crop/denoise/contrast của snapshot. Sau retry item, backend tái tạo response batch từ raw cache.
- **FR-032:** Trong ngữ cảnh Inbox, modal MUST cho phép xem preview/raw OCR text, sửa field và `Xác nhận`. Đóng `x` giữ raw OCR nhưng bỏ chỉnh sửa chưa xác nhận; mở lại dùng OCR result đã có. `Xác nhận` trả dữ liệu về module để xuất JSON/Excel và MUST NOT ghi Stage/Pool/Diagram.
- **FR-033:** Chốt output MUST nguyên tử ở mức batch: backend chỉ ACK đúng một output-selection cho mỗi `batch_id`, và tập output cùng preview snapshot được freeze trong cùng thao tác đó. Mọi selection đến sau MUST bị từ chối, kể cả khi mang tập output khác; lặp lại đúng selection đã ACK trả về kết quả cũ. Tác vụ tạo output MUST idempotent theo `(batch_id, output_type)`.
- **FR-034:** Các timestamp MUST lưu nội bộ bằng UTC; tên file và thời gian hiển thị cho user MUST dùng `Asia/Ho_Chi_Minh`.
- **FR-035:** Nếu preview không còn item, hệ thống MUST không cho chọn output và chỉ cho quay lại Inbox tạo lô mới. Batch `Hết hạn` là trạng thái kết thúc và không được coi là chưa hoàn tất. Một lô chưa hết hạn được coi là chưa hoàn tất khi còn ít nhất một trong: item đang `Đang chuẩn bị`/`Lỗi`, preview `Chờ duyệt` chưa chốt output, OCR gate tồn tại nhưng chưa `Đã xác nhận`, hoặc output đã chọn chưa ở trạng thái cuối (`Sẵn sàng` hoặc `Lỗi` tất định không retry được). Lô có output trạng thái lẫn lộn vẫn là chưa hoàn tất nếu bất kỳ output nào còn `Đang tạo` hoặc còn `Thử lại`. Khi `Lô gần nhất` chưa hoàn tất, `Tạo lô` mới MUST hiển thị link lô cũ để mở/lưu và chờ user xác nhận trước khi tiếp tục.
- **FR-036:** Connector MUST giữ source media tới khi backend tạo working copy thành công. Nếu source mất trước `Xử lý`, validation toàn lô MUST thất bại, giữ lựa chọn và hiển thị `File nguồn không còn`; user phải bỏ item hoặc nhận lại media. Sau khi batch được ACK, mọi preprocess/OCR/export/retry MUST dùng working copy phía backend.
- **FR-037:** Mỗi raw OCR item và mỗi normalized person/property MUST truy nguyên được tới một hoặc nhiều `input_item_id`. Trong JSON export, mỗi `raw_results` item MUST vật chất hóa `input_item_id`, `source_display_name`, `sent_at` và, nếu đến từ PDF, `page_number`/`page_count`; `source_refs` của normalized record trỏ tới các `input_item_id` này mà không đổi top-level keys. Excel thêm `Nguồn`, `Thời điểm`, `Trang` cho từng row; nếu record có nhiều source ref thì các giá trị phân biệt được nối bằng `; ` theo thứ tự `source_refs`. File JSON/Excel đã tải MUST vẫn tự đối chiếu được sau khi batch bị cleanup.
- **FR-038:** Trước khi triển khai lát OCR/JSON/Excel hoặc tuyên bố toàn module production-ready, runtime `POST /api/ocr/analyze` MUST được đồng bộ với parent spec trong một task shared-OCR được user phê duyệt riêng: mọi nhánh QR OCR (`try_decode_qr`, `_append_qr_person`, QR fallback/priority và `source_priority` liên quan) MUST bị loại khỏi active Cloud AI OCR runtime; 100% item OCR phải gọi model, rồi backend parser/regex trả `properties`/`persons` cho CCCD, sổ đỏ và giấy khai tử. Gate này MUST NOT âm thầm mở rộng scope hoặc sửa shared OCR trong lát Zalo source/realtime/Data Sync; các lát Zalo intake MAY triển khai và kiểm thử độc lập, nhưng OCR/output vẫn bị khóa cho tới khi parent/runtime mismatch được giải quyết.
- **FR-039:** Connector MUST có hard quota theo tổng dung lượng media nguồn, cấu hình được, và MAY có thêm retention theo tuổi. Khi chạm quota, connector MUST dọn media không còn được batch chưa hết hạn tham chiếu trước; nếu media được bảo vệ cộng object mới vẫn vượt quota thì connector MUST tạm dừng nhận/publish media mới, hiển thị trạng thái `Bộ nhớ nhận Zalo đã đầy`, không evict media được bảo vệ và tự tiếp tục khi có dung lượng. Giá trị quota/retention được chốt theo tài nguyên deployment.
- **FR-040:** Mỗi raw text MUST lưu tối thiểu connector account, conversation, message ID, sender ID dạng opaque, sent time, received time và nội dung nguyên văn; duplicate cùng khóa trả bản ghi cũ, payload khác cùng khóa bị từ chối. Text MUST không xuất hiện trong production log, notification, LLM/classification/action hoặc OCR/export trong revision này.
- **FR-041:** UI MUST giữ đúng ba trạng thái chính theo R-019. Khi ở `Mất kết nối`, UI MUST hiển thị thêm đúng một lý do `Đang tự kết nối lại` hoặc `Connector đã dừng`; `Cần đăng nhập lại` luôn thắng các lý do này. UI MUST hiển thị `Có thể thiếu event từ …` cho mọi khoảng listener không nhận liên tục. Gap recovery MUST chỉ chạy khi user bấm Data Sync, MAY giảm gap nhưng MUST NOT tự xóa cảnh báo hoặc tuyên bố đầy đủ; onboarding, session restore và reconnect MUST NOT tự sync history.
- **FR-042:** Text và media MUST có quota/retention cấu hình độc lập. Text hết retention hoặc khi chạm text quota được xóa từ cũ nhất; text không có batch-protection và không có export trong revision này. Nếu dọn text cũ vẫn không đủ chỗ, hệ thống chỉ tạm dừng text intake, hiển thị `Bộ nhớ chat đã đầy`, tiếp tục media intake nếu media quota còn chỗ và tự tiếp tục text khi có dung lượng. Media tiếp tục dùng protection/quota của FR-039; hệ thống MUST báo rõ intake nào đang dừng.
- **FR-043:** Source Sync MUST chỉ cập nhật metadata, tự chạy khi login/session restore, `friend_event`/`group_event`, listener reconnect, targeted unknown-thread lookup và reconciliation mỗi 60 phút, đồng thời có nút `Làm mới nguồn`. Full reconciliation từ `getAllFriends`/`getAllGroups` chỉ bao phủ friends/groups; strangers được discovery opportunistically từ event/history có định danh, không được hứa là inventory đầy đủ. Source Sync MUST NOT lấy history, text hoặc media. Modal MUST xếp source có activity theo activity giảm dần, source chưa activity theo alphabet và tách strangers rõ ràng.
- **FR-044:** `My Documents` MUST là source riêng mặc định `BẬT`, dùng tên hiện tại thay cho `Zalo Cloud`; connector MUST chỉ gán self-event vào source này khi `threadId == session send2me_id`, không nhận mọi outgoing self-message. Realtime MUST còn là live-verification gate và history MUST không được cam kết trước live spike.
- **FR-045:** `Đồng bộ dữ liệu` MUST disabled khi chưa persisted consent, trạng thái chính khác `Đã kết nối`, account còn policy `Đang áp dụng` hoặc đang có một run active; đây là trigger duy nhất của Data Sync và hệ thống MUST NOT prefetch/cache history. Khi bấm, backend MUST chốt `cutoff_at` và snapshot ID source `BẬT` đã ACK, loại mọi source `Đang áp dụng` và `My Documents` trước khi live spike history được duyệt, rồi gửi snapshot này trực tiếp cho run thay vì phụ thuộc config cache 15 giây. Connector MUST gửi đúng một `requestOldMessages(User)` và một `requestOldMessages(Group)` ở phạm vi thread-type toàn account, xử lý nền có giới hạn, ưu tiên realtime và dùng cùng idempotency key với realtime.
- **FR-046:** Data Sync MUST lọc từng response cục bộ theo source snapshot và `sent_at` trong cửa sổ tối đa 7 ngày trước `cutoff_at`; filter cục bộ MUST authoritative vì upstream không có count/window/completeness guarantee. Toggle sau khi run bắt đầu MUST không đổi snapshot. Chỉ text và JPG/JPEG/PNG/PDF còn tải được mới import. Media URL hết hạn/không tải được MUST chỉ được count/report failure và MUST NOT tạo placeholder.
- **FR-047:** Data Sync MUST có ba trạng thái tối thiểu `Đang đồng bộ`, `Hoàn tất best-effort`, `Lỗi` và hiển thị progress/result gồm `received` (message event vượt qua source snapshot + local 7-day filter), `duplicates` (idempotency key đủ điều kiện đã tồn tại), `imported text` (raw text record mới), `imported media` (attachment mới tải/publish thành công), `media download failures` (attachment đủ điều kiện nhưng không tải được). Run hoàn tất khi nhận xong hai response và xử lý hết backlog; thiếu response quá timeout cấu hình, lỗi request/processing hoặc listener ngắt làm run `Lỗi`. Item đã ACK được giữ; chạy lại an toàn. Kết quả MUST luôn ghi best-effort, không tự xóa gap warning và không tuyên bố completeness.
- **FR-048:** Connector source load MUST theo event volume, không dựa trên giả định danh sách tĩnh khoảng 1.000 nguồn. Source reconciliation MUST NOT poll Zalo mỗi 15 giây; polling 15 giây hiện có chỉ dành cho backend policy/config propagation và MUST tách biệt với source reconciliation mỗi 60 phút. Sau consent hoặc toggle, UI MUST giữ trạng thái `Đang áp dụng` cho tới khi connector ACK policy version mới; source đang chờ ACK MUST fail-closed cho content mới và chỉ sau ACK mới được báo sẵn sàng theo lựa chọn mới.

## 6. Business data and source of truth

| Data | Meaning | Source of truth | Required | Validation/business rule |
| --- | --- | --- | --- | --- |
| Zalo source | Metadata hội thoại gồm loại `friend`, `group`, `stranger` hoặc `my_documents`, định danh/tên và activity gần nhất nếu có | Source Sync + cấu hình Zalo Document Inbox | Yes | Friends/groups và `My Documents` mặc định `BẬT`, strangers mặc định `TẮT`; explicit toggle theo connector account thắng default và reclassification |
| Zalo event metadata | ID/loại nguồn, thời điểm, sender/message ID và attachment metadata nếu có | Realtime outbox hoặc Data Sync trước ACK; Inbox sau ACK | Yes | Realtime và Data Sync dùng cùng khóa R-024; duplicate giống hệt không tạo bản ghi mới |
| Zalo chat text | Raw text dùng cho research cùng provenance tối thiểu | Inbox sau ACK | Conditional | Chỉ từ source bật qua realtime hoặc Data Sync; không production log/LLM/action/export; quota/retention độc lập theo FR-042 |
| Data Sync run | Consent/account, `cutoff_at`, source-ID `BẬT` đã ACK snapshot, trạng thái, progress và kết quả best-effort | Zalo Document Inbox | Conditional | Một run active/account; chỉ do user bấm khi connected; loại `My Documents` trước live-spike approval; giữ các count FR-047; chạy lại idempotent và không biểu thị completeness |
| `media_object_key` | Tham chiếu server-side tới media nguồn | Connector/shared storage | Yes | Opaque, bind với connector account; object phải immutable/readable trước ACK |
| Original image | Media nguyên bản nhận từ Zalo | Storage của connector | Yes | Bất biến đối với Zalo Document Inbox; connector áp retention/quota cấu hình được nhưng không xóa media của batch chưa hết hạn |
| Original PDF | Tài liệu PDF nguyên bản nhận từ Zalo | Storage của connector | Conditional | Bất biến đối với Zalo Document Inbox; connector áp retention/quota cấu hình được nhưng không xóa media của batch chưa hết hạn |
| Rendered PDF page | Ảnh tạo từ từng trang PDF | Backend sau `Xử lý` | Conditional | Thay PDF tại đúng vị trí bằng `P1..Pn`; giữ tên nguồn và `trang n/N` |
| Batch/preview state | Preparation state, item, thứ tự, crop/no-crop, snapshot và expiry | Browser trước `Xử lý`; backend sau validation | Yes | Trước `Xử lý` không khôi phục; output selection freeze snapshot; toàn batch dùng một expiry 72 giờ |
| Processed image | Bản toàn khung hoặc crop, sau đó làm sạch/resize | Kết quả tiền xử lý | No | Có thể tạo lại từ file gốc; crop là tùy chọn riêng |
| `input_item_id` | ID ổn định của ảnh/trang trong snapshot | Batch backend | Yes | Opaque; dùng cho OCR cache, retry và provenance |
| Raw OCR result | Text/payload chưa chuẩn hóa từ model | Cloud AI OCR response/cache | No | Gắn `input_item_id`, `source_display_name`, `sent_at` và trang PDF nếu có; retry item không xóa raw result item khác |
| Normalized OCR JSON | Dữ liệu giấy tờ đã qua parser/regex và user kiểm tra | Zalo Document Inbox | No | Đúng contract mục 6.1; `source_refs` resolve được qua provenance đã vật chất hóa trong `raw_results` |
| OCR gate | Một lần review dùng chung cho JSON/Excel | Batch backend | Conditional | `Chờ xác nhận` giữ raw OCR; mở lại không gọi model |
| Export file | JSON, Excel hoặc PDF đã chọn | Kết quả xuất | No | Idempotent theo `(batch_id, output_type)`; cột/field nguồn được vật chất hóa lúc export để còn đối chiếu sau cleanup; trạng thái theo R-030 |

### 6.1 JSON and Excel field contract

- JSON MUST giữ các top-level key hiện có của `POST /api/ocr/analyze`: `persons`, `properties`, `marriages`, `raw_results`, `errors`, `summary`. Module này không trích giấy đăng ký kết hôn nên `marriages` giữ mảng rỗng.
- `raw_results` giữ raw OCR text/payload cùng `input_item_id`, `source_display_name`, `sent_at` và `page_number`/`page_count` nếu đến từ PDF; `persons`/`properties` là dữ liệu đã parse và user xác nhận, mỗi record có `source_refs` chứa một hoặc nhiều `input_item_id` mà không đổi top-level keys.
- Mỗi phần tử `persons` dùng contract chung `ho_ten`, `so_giay_to`, `ngay_sinh`, `gioi_tinh`, `dia_chi`, `ngay_cap`, `noi_cap`, `ngay_het_han`, `place_of_origin`, `ngay_chet`; giấy khai tử chỉ bổ sung giá trị đặc thù `ngay_chet`, các field không có trên giấy để trống.
- Mỗi phần tử `properties` dùng các field hiện có `loai_so`, `so_serial`, `so_vao_so`, `so_thua_dat`, `so_to_ban_do`, `dien_tich`, `dia_chi`, `chu_su_dung`, `ngay_cap`, `co_quan_cap`, `loai_dat`, `thoi_han`, `hinh_thuc_su_dung`, `nguon_goc`, `land_rows`.
- Excel sheet `Nguoi` dùng các field scalar của `persons`; sheet `So_do` dùng các field scalar của `properties`. Mỗi row thêm `Nguồn`, `Thời điểm`, `Trang` để đối chiếu với media; record có nhiều source ref nối các giá trị phân biệt bằng `; ` theo thứ tự `source_refs`. `land_rows` chỉ nằm trong JSON ở phiên bản đầu, không tạo sheet hoặc cột JSON riêng trong Excel.
- Chỉ tạo sheet Excel có ít nhất một bản ghi; không tạo sheet cho `raw_results`, `errors`, `summary` hoặc `marriages`.

## 7. Edge cases and failure behavior

- Missing data: Trường OCR thiếu được để trống và cảnh báo; không tự bịa dữ liệu.
- Conflicting data: Giữ giá trị nguồn/raw và yêu cầu người dùng kiểm tra.
- Unsupported document: Ảnh thuộc định dạng hỗ trợ vẫn ở Inbox và có thể OCR; nếu không thuộc CCCD/sổ đỏ/khai tử thì parser cảnh báo chưa hỗ trợ, không bịa dữ liệu.
- Source Sync failure: Giữ inventory/toggle đã lưu, báo refresh thất bại và chờ trigger kế tiếp hoặc `Làm mới nguồn`; không suy ra source bị xóa và không lấy history để bù.
- Unknown friend/group: Giữ chính event trong xử lý có giới hạn tới khi targeted lookup resolve source; sau resolve áp default/explicit choice rồi tiếp tục event, không biến event thành stranger chỉ vì lookup tạm lỗi.
- Unknown stranger: Chỉ ghi metadata tối thiểu ở `TẮT`; không lưu raw text, không tải media và không tạo placeholder từ event đầu tiên.
- Stranger reclassified: Đổi loại thành friend; giữ explicit toggle nếu có, nếu không áp friend default `BẬT`.
- `My Documents`: Chỉ self-event khớp `session send2me_id` được xét; realtime chưa qua live verification và history chưa qua live spike không được mô tả là hỗ trợ.
- Unsupported media: Video, voice, sticker và file khác bị bỏ tại connector, không tải, lưu hoặc tạo placeholder; raw text được hỗ trợ theo R-037.
- Recalled message: Không đồng bộ thu hồi; media đã tải không bị Zalo Document Inbox tự xóa và tiếp tục theo lifecycle nguồn của connector.
- Unsafe crop: Dùng bản toàn khung đã tiền xử lý và cảnh báo; không tự cắt khi không tìm được hình chữ nhật đủ tin cậy.
- Connector offline: Không xóa inbox; hiển thị trạng thái và cho đăng nhập/kết nối lại.
- Stale/replayed state: Backend dùng `received_at` và listener generation; heartbeat cũ không được đánh dấu listener mới là online.
- Duplicate image: Hai khóa media `(connector_account_id, conversation_id, msg_id, attachment_index)` khác nhau vẫn hiển thị riêng dù ảnh giống nhau; người dùng quyết định giữ hay bỏ trước khi xử lý.
- Duplicate selection: Cùng một media/trang chỉ xuất hiện một lần trong một lô; chọn lặp không tạo bản thứ hai.
- Duplicate webhook delivery: Cùng một khóa idempotency được gửi lại chỉ ACK bản ghi đã có, không tạo thêm media.
- Conflicting webhook delivery: Cùng khóa idempotency nhưng payload khác bị từ chối, không overwrite bản ghi đã có.
- Missing source: Media nguồn mất trước khi backend tạo working copy bị đánh dấu `File nguồn không còn`; user phải bỏ item hoặc nhận lại media.
- Oversized batch: Vi phạm một giới hạn làm toàn bộ `Xử lý` thất bại trước khi tạo batch; không tự chia lô hoặc bỏ item.
- Realtime attachment download failure: Connector tự retry và chỉ publish khi thành công; Inbox không hiển thị attachment lỗi và không có nút retry download. Data Sync history khác ở chỗ URL hết hạn/không tải được phải tăng failure count theo FR-046/FR-047.
- Preparation failure: Item tách PDF/preprocess lỗi có `Thử lại`/`Bỏ`; batch chưa vào `Chờ duyệt` và chưa chọn được output cho tới khi mọi item còn lại đã xong.
- Parse failure: OCR thành công nhưng parse/pair/shape lỗi thì OCR gate ở `Lỗi`; `Thử lại` chỉ chạy lại từ raw cache, không gọi model.
- Terminal error: Lỗi tất định như Excel rỗng không có `Thử lại`; user phải tạo lô mới.
- Duplicate output selection: Một `batch_id` chỉ ACK một output-selection; selection sau bị từ chối kể cả khi khác tập output.
- OCR page failure: Giữ kết quả trang thành công nhưng không tạo JSON/Excel partial; retry chỉ gọi model cho trang lỗi.
- Export failure: Giữ dữ liệu đã xác nhận và chỉ tạo lại file lỗi; không OCR hoặc xác nhận lại.
- Empty Excel: Không tạo workbook không có sheet; output `Lỗi` với lý do không có dữ liệu và không có `Thử lại`.
- Partial PDF conversion: Không đưa lô vào xử lý âm thầm nếu thiếu trang; hiển thị rõ trang lỗi và cho phép thử lại hoặc bỏ trang đó.
- Invalid PDF: PDF hỏng, có mật khẩu hoặc sai loại làm toàn bộ `Xử lý` thất bại trước khi tạo batch; lỗi chỉ rõ item, lựa chọn browser vẫn còn để user bỏ item đó rồi thử lại.
- Source storage full: Connector dọn media không được batch chưa hết hạn tham chiếu trước; nếu vẫn vượt hard quota thì dừng nhận/publish media mới, hiển thị `Bộ nhớ nhận Zalo đã đầy`, không evict media được bảo vệ và tự tiếp tục khi có dung lượng.
- Webhook unavailable: Zalo connector giữ bền vững sự kiện/media trong outbox và thử gửi lại khi `notary_v2` hoạt động.
- Data Sync unavailable: Nút `Đồng bộ dữ liệu` disabled khi chưa consent, disconnected, còn policy `Đang áp dụng` hoặc đã có run active; không tạo job và không prefetch/cache history.
- Data Sync interrupted: Thiếu một response quá timeout cấu hình, lỗi request/processing hoặc listener ngắt làm run `Lỗi`; giữ item đã ACK, đóng run và cho phép chạy lại khi connected.
- Partial/oversized history response: Tiếp tục xử lý nền có giới hạn, ưu tiên realtime, áp source snapshot + local 7-day filter và báo các count thực nhận; không suy diễn response là đầy đủ.
- Expired media URL in history: Tăng `media download failures`; không tạo media record/placeholder giả. User có thể chạy lại, nhưng kết quả vẫn best-effort.
- Listener reconnecting: Event xảy ra khi WebSocket chưa mở có thể thiếu; UI ghi mốc bắt đầu khoảng gián đoạn, không tự Data Sync và không gọi trạng thái sau reconnect là đồng bộ đầy đủ.
- Listener retry exhausted/unsupported close code: Listener đóng hẳn; UI dùng trạng thái chính `Mất kết nối` với lý do `Connector đã dừng`. Nếu session đồng thời không dùng được thì chuyển sang `Cần đăng nhập lại` theo priority R-019; cả hai trường hợp giữ mốc có thể thiếu event.
- Duplicate Zalo connection: Mở listener khác cho cùng tài khoản (ví dụ Zalo Web/connector khác) có thể đá listener hiện tại; hệ thống báo mất kết nối, không giả định event trong khoảng đó sẽ được phát lại.
- Parent/backend shutdown: FastAPI shutdown/restart chủ động terminate connector; mọi event tới trước khi listener mới `Đã kết nối` có thể thiếu, còn outbox đã ghi vẫn được gửi lại sau khi connector chạy lại.
- Closed OCR modal: Bỏ chỉnh sửa chưa xác nhận nhưng giữ raw OCR và OCR gate `Chờ xác nhận`; mở lại không gọi model.
- Expired batch: Tới expiry chung 72 giờ, request xác nhận/retry/download mới bị từ chối; job hoàn tất sau expiry không được publish và dữ liệu tạm được cleanup.
- Empty batch: Bỏ hết item trong preview thì không cho chọn output; chỉ cho quay lại Inbox tạo lô mới.
- Superseded batch: Cảnh báo tạo lô mới phải hiển thị link lô cũ để user mở/lưu; lô cũ vẫn sống đến hết hạn nhưng không còn là `Lô gần nhất`.
- Behavior that must never occur: Ghi đè ảnh gốc, log session/cookie/field value, mất ảnh do OCR/export lỗi, tự đưa dữ liệu vào hồ sơ, tự xử lý ảnh khi user chưa yêu cầu, buộc user phân loại giấy tờ hoặc đổi contract upload-file của OCR endpoint.

## 8. Measurable success criteria

- **SC-001:** Người dùng xử lý được một lô ảnh Zalo thành JSON, Excel hoặc PDF mà không tải ảnh thủ công qua điện thoại/CamScanner.
- **SC-002:** Không ảnh nào bị tự động ẩn hoặc loại vì hệ thống cho rằng ảnh bị trùng.
- **SC-003:** `[A, PDF, B]` tạo preview `[A, P1..Pn, B]`; thứ tự user xác nhận khớp PDF đầu ra và thứ tự gửi OCR.
- **SC-004:** Preparation/OCR/export lỗi không làm mất working copy, preview state hoặc bước đã thành công.
- **SC-005:** Backend parser/regex tạo đúng field contract mục 6.1 cho CCCD, sổ đỏ và giấy khai tử, đồng thời giữ raw OCR text khi chưa nhận đủ trường.
- **SC-006:** Webhook retry cùng component key không tạo text/media thứ hai; một message có cả raw text và nhiều attachment tạo đúng một text record cùng các media theo `attachment_index`, không bị coi là payload conflict, còn hai media key khác nhau vẫn hiển thị riêng dù nội dung ảnh giống nhau.
- **SC-007:** Xuất PDF không gọi Cloud AI OCR; JSON và Excel được chọn cùng lúc từ một lô chỉ dùng một kết quả OCR.
- **SC-008:** Batch validation thành công hết hạn sau đúng 72 giờ từ `created_at`; cleanup không xóa media nguồn hoặc dữ liệu đã chuyển vào luồng chính.
- **SC-009:** Module chỉ chạy local/mạng nội bộ tin cậy khi platform chưa có auth và đi qua cơ chế đó ngay khi có; browser không nhận filesystem path/session Zalo và production log không chứa định danh Zalo thô, tên file nguồn, `before`/`after` hoặc field value.
- **SC-010:** Khi tab Inbox visible và backend hoạt động, event đã ACK xuất hiện ở lần polling thành công kế tiếp với chu kỳ mặc định 2 giây; focus/visible lại gây refresh ngay.
- **SC-011:** Backend Inbox dùng multipart `files` với opaque `input_item_id` và giữ top-level response keys của OCR endpoint; modal chỉ review cache và JSON/Excel phản ánh field user xác nhận.
- **SC-012:** Reload sau `Xử lý` khôi phục preparation/preview state; output selection freeze snapshot và job tiếp tục phía backend sau ACK dù tab đóng.
- **SC-013:** Đóng/mở modal không gọi OCR lại; retry item chỉ OCR item lỗi rồi tái parse/pair/shape toàn snapshot, và một item lỗi ngăn mọi JSON/Excel partial.
- **SC-014:** PDF có thể `Sẵn sàng` độc lập; OCR gate và mỗi lỗi có thể khắc phục có đúng hành động retry tương ứng mà không chạy lại bước thành công, còn lỗi tất định không hiển thị retry.
- **SC-015:** Re-consent policy mới áp default cho inventory legacy thiếu provenance; sau policy ACK, friends/groups và `My Documents` mặc định `BẬT`, strangers mặc định `TẮT`. Listener vẫn nhận event không phụ thuộc toggle; unknown friend/group được resolve rồi xử lý event đầu, unknown stranger chỉ tạo metadata không content, explicit toggle không bị refresh/relogin/reclassification ghi đè, và nguồn `Đang áp dụng` fail-closed tới ACK.
- **SC-016:** Tên file tải và `Hết hạn lúc …` hiển thị theo `Asia/Ho_Chi_Minh` bất kể timezone hệ điều hành server.
- **SC-017:** Lô rỗng không tạo output; cảnh báo thay lô hiển thị link lô cũ để mở/lưu trước khi tiếp tục, còn batch `Hết hạn` không gây cảnh báo chưa hoàn tất.
- **SC-018:** Lô vượt 20 MB/file, 100 ảnh/trang hoặc giới hạn tổng byte/pixel đã cấu hình bị từ chối nguyên tử trước khi tạo batch; thay đổi cấu hình phản ánh đúng lỗi hiển thị.
- **SC-019:** Webhook replay/xung đột/sai binding bị từ chối; media chỉ ACK khi object cùng namespace đọc được và size/type thực khớp.
- **SC-020:** Mỗi normalized record JSON resolve `source_refs` được tới nguồn/thời điểm/trang đã vật chất hóa trong `raw_results`; mỗi row Excel có các cột nguồn tương ứng, kể cả khi record tham chiếu nhiều input item.
- **SC-021:** Heartbeat mặc định 15 giây và stale threshold 45 giây tạo đúng ba trạng thái `Đã kết nối`, `Cần đăng nhập lại`, `Mất kết nối` theo ưu tiên đã định, mà heartbeat generation cũ không thể đảo trạng thái mới và chỉ QR login thành công mới thoát `Cần đăng nhập lại`.
- **SC-022:** Item preparation `Lỗi`/`Đang chuẩn bị` chặn được việc chọn output; parse lỗi retry được từ raw cache mà không phát sinh model call.
- **SC-023:** Hai output-selection đồng thời trên cùng `batch_id` chỉ có một được ACK; tập output sau khi freeze không thay đổi được.
- **SC-024:** File JSON/Excel đã tải vẫn đối chiếu được tới hội thoại/thời điểm/trang sau khi batch bị cleanup.
- **SC-025:** Connector giữ media nguồn trong hard quota bằng cách dọn media không được bảo vệ hoặc tạm dừng nhận/publish media mới; không xóa media của batch chưa hết hạn và tự tiếp tục khi có dung lượng.
- **SC-026:** Trước implementation, active Cloud AI OCR runtime không còn bất kỳ nhánh QR OCR/fallback/priority nào; 100% item OCR gọi model lấy raw text/payload và backend parser/regex trả đúng `persons`/`properties` cho CCCD, sổ đỏ, giấy khai tử.
- **SC-027:** Source Sync chạy đủ các trigger R-033, chỉ đổi metadata, có refresh thủ công, reconciliation 60 phút và không lấy history/media; modal xếp theo activity giảm dần, rồi alphabet cho nguồn chưa activity, với strangers tách riêng.
- **SC-028:** Mỗi raw text nhận từ source bật có provenance/idempotency, không xuất hiện trong production log và không tự kích hoạt LLM, classification, action hoặc export; text quota pressure không dừng media.
- **SC-029:** Mọi khoảng listener không nhận liên tục dùng đúng ba trạng thái chính và lý do dưới `Mất kết nối`; không tự chạy history khi onboarding/reconnect, còn Data Sync thủ công chỉ có thể giảm gap và không chứng minh đầy đủ.
- **SC-030:** Khi đã consent và connected, một Data Sync snapshot source `BẬT` đã ACK + cutoff, loại `My Documents` trước live-spike approval, gửi đúng hai request type-wide User/Group, áp local 7-day filter, dùng cùng idempotency với realtime và báo đủ năm count; chạy lại không tạo duplicate.
- **SC-031:** Data Sync disabled khi chưa consent, disconnected, còn policy `Đang áp dụng` hoặc có run active; không prefetch/cache history. Run có trạng thái `Đang đồng bộ`/`Hoàn tất best-effort`/`Lỗi`, timeout không treo vô hạn; realtime được ưu tiên và media URL hỏng chỉ tăng failure count, không tạo placeholder.
- **SC-032:** Chỉ self-event có `threadId == session send2me_id` được xét cho `My Documents`; realtime không được coi production-ready trước live verification và history không được cam kết trước live spike.
- **SC-033:** Source reconciliation không phát request Zalo theo polling 15 giây; 15 giây chỉ kiểm tra backend policy/config, reconciliation nguồn cách 60 phút và xử lý tải theo event volume thay vì giả định khoảng 1.000 nguồn tĩnh.

## 9. Assumptions and dependencies

- Connector Zalo cá nhân hoạt động bằng API không chính thức và có rủi ro phiên đăng nhập/điều khoản nền tảng.
- `notary_v2` tiếp tục cung cấp modal, multipart-file endpoint và top-level Cloud AI OCR response contract hiện hành; parser/field contract được mở rộng theo mục 6.1.
- `notary_v2` hiện chưa có user authentication/authorization ở `main.py`; module này không xây auth mới mà chấp nhận ràng buộc triển khai local/mạng nội bộ tin cậy theo R-026, và sẽ dùng cơ chế access control của platform ngay khi có.
- `docs/platform/document-intake/spec.md` đã chốt pure Cloud OCR nhưng `routers/ocr_ai.py` vẫn decode QR và cho QR thắng AI trong `source_priority`; đây là runtime mismatch bắt buộc xử lý theo FR-038. Việc loại QR chỉ áp dụng cho OCR nội dung giấy tờ, không áp dụng cho QR login của Zalo connector.
- Các biến thể biểu mẫu thực tế của CCCD, sổ đỏ và giấy khai tử chưa được chuẩn hóa/bao phủ đầy đủ. Kiến trúc đã chốt là `ảnh -> raw OCR text/payload -> backend parser/regex -> user xác nhận -> JSON`; trước khi coi một nhóm giấy tờ là production-ready, phải chuẩn hóa field mapping, tập mẫu và regression test cho parser của nhóm đó. Không dùng model trả thẳng normalized JSON để né bước chuẩn hóa này trong MVP.
- Trong sử dụng thực tế, một PDF thường có dưới 20 trang và hiếm khi vượt 50 trang. Đây là capacity assumption để thiết kế/test, không phải hard limit; giới hạn 100 ảnh/trang cùng tổng byte/pixel budget cấu hình được theo FR-029 vẫn giữ nguyên.
- Zalo connector dùng trực tiếp dependency `zca-js` được pin chính xác; không fork upstream nếu chưa có thiếu sót bắt buộc đã được kiểm chứng bằng payload thực tế.
- `zca-js` chỉ cung cấp kết nối/sự kiện Zalo; connector của dự án chịu trách nhiệm tải media, bảo vệ session, ký webhook, lưu outbox và retry đến khi ACK.
- Mỗi tài khoản chỉ vận hành một web listener; mở Zalo Web song song có thể làm listener dừng và phải được phản ánh bằng trạng thái kết nối/lỗi.
- Bản local và bản deploy dùng cùng hành vi UI/API; folder local chỉ phục vụ môi trường phát triển trên máy chạy backend, còn bản deploy lưu media, ảnh dẫn xuất và output trong storage phía server.
- Storage local/object-store phải cùng thực hiện contract `media_object_key`; connector giữ source ít nhất tới khi backend ACK working copy, sau đó batch không phụ thuộc source.
- Backend giữ idempotency receipt cùng vòng đời Inbox event để retry muộn không tạo lại media; connector chỉ xóa outbox entry sau ACK hợp lệ.
- Với request từ Inbox, các trường logging mà contract OCR cha gọi là `filename`, `before`, `after` phải dùng opaque/redacted value trong production; không log PII để “đủ field”.
- Wire types/enums, signature format, replay window, ACK status code, retry backoff, storage adapter và cleanup schedule thuộc technical contract; chúng không được thay đổi hành vi chuẩn hóa trong spec này.
- Timestamp lưu nội bộ bằng UTC và hiển thị/tạo tên file theo `Asia/Ho_Chi_Minh`, không phụ thuộc timezone hệ điều hành server.
- Trước persisted intake consent, người dùng chịu trách nhiệm bảo đảm có quyền thu thập text/media trong phạm vi source policy; user có thể tắt nguồn cần loại trừ bất kỳ lúc nào.
- `requestOldMessages` là upstream best-effort, không có count/window/completeness guarantee; response có thể thiếu và local `sent_at` filter mới là ranh giới 7 ngày authoritative.
- Khả năng nhận realtime của `My Documents` và payload nhận diện qua `session send2me_id` chưa được chứng minh bằng live account; history của source này còn unproven và không nằm trong cam kết Data Sync trước live spike.
- Source inventory có thể lớn hoặc nhỏ theo tài khoản; capacity phải theo event volume, không dựa trên giả định khoảng 1.000 nguồn cố định.
- Giao diện tối ưu cho máy tính nội bộ; mobile full-sync/decrypt không thuộc phạm vi đầu tiên.

## 10. Unresolved questions and remaining risks

Spec giữ `DRAFT` để user duyệt bản viết này. Các quyết định product đã chốt; các gate/risk sau không được biến thành cam kết trước khi có evidence:

- [LIVE VERIFICATION] Realtime `My Documents`: xác nhận trên live account rằng event đúng được nhận và chỉ `threadId == session send2me_id` được phân loại vào source này; mọi outgoing self-message khác bị loại khỏi quy tắc.
- [LIVE SPIKE] `My Documents` history: hiện unproven và không nằm trong cam kết Data Sync cho tới khi live spike chứng minh API/payload/media behavior.
- [UPSTREAM RISK] `requestOldMessages` User+Group là best-effort, không có count/window/completeness guarantee; response có thể thiếu và local 7-day filter là authoritative nhưng không chứng minh completeness.
- [DEPLOYMENT] Giá trị hard quota/retention media theo FR-039 và quota/retention text độc lập theo FR-042.
- [DEPLOYMENT] Xác nhận default tổng byte và pixel budget theo RAM/hạ tầng thực tế của server.
- [RESEARCH] LLM local, taxonomy phân loại và mọi action/export từ text thuộc spec riêng; chưa được phép chạy trên raw text đã lưu.
- [IMPLEMENTATION GATE] Lát Zalo source/realtime/Data Sync không sửa shared OCR. Trước lát OCR/JSON/Excel và trước khi tuyên bố toàn module production-ready, mở task shared-OCR riêng theo FR-038 để đồng bộ `POST /api/ocr/analyze` với parent spec; không âm thầm đổi OCR contract hoặc gom ba file OCR dirty vào implementation Zalo.
- [IMPLEMENTATION RISK] Chuẩn hóa field mapping, tập mẫu và regression test parser/regex cho CCCD, sổ đỏ, giấy khai tử; user review/xác nhận vẫn bắt buộc cho tới khi từng nhóm đạt gate.
- [CAPACITY ASSUMPTION] Test tải chính tập trung vào PDF dưới 20 trang, có case hiếm trên 50 trang và boundary 100 ảnh/trang/tổng byte/pixel; số trang thường gặp không thay validation an toàn.

## Approval

- Status: `APPROVED`
- Previous approval: 2026-08-04, trước revision source discovery/realtime/Data Sync.
- Product design source: User-approved decisions supplied for revision 2026-08-07.
- Written-spec approval: User approved 2026-08-07.

## Agent self-check before requesting approval

- [x] The routed authoritative documents were read and linked.
- [x] Legal rules, product conventions, and observed behavior are not mixed.
- [x] Terms have one precise meaning in this context.
- [x] Each resolved requirement is observable and has an acceptance scenario.
- [x] Important edge, error, and forbidden cases are explicit.
- [x] Scope and out-of-scope are explicit.
- [x] Integration behavior is normative; wire-level and implementation details are deferred to the technical contract.
- [x] Workflow, UX states and result lifecycle are decided end to end.
- [x] Claims about current runtime were verified against the code (`main.py` has no auth; `routers/ocr_ai.py` still prefers QR over AI).
- [x] Section 10 không còn quyết định product behavior mở; live verification/spike, upstream incompleteness và deployment values được giữ rõ như risk/gate.
- [x] Source-type defaults, first-event handling, consent, realtime/history, persistence và quota/retention đã được cross-check thành ma trận nhất quán.
- [x] Parent OCR contract được giữ nguyên; revision này không thay OCR behavior/runtime hoặc các file shared-core.
- [x] The agent has summarized the revised spec in plain business language for user review.
- [x] The user approved this written revision before status changed to `APPROVED`.
