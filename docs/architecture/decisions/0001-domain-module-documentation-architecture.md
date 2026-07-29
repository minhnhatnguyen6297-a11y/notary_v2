# ADR-0001: Tổ chức tài liệu theo domain module

- Status: Accepted
- Date: 2026-07-28
- Scope: Cấu trúc tài liệu và quy tắc định tuyến tri thức cho agent

## Bối cảnh

Tài liệu hiện được chia ngang qua `docs/plans`, `docs/specs`, `docs/issues`,
`docs/changelog`, `docs/learning` và `docs/superpowers`. Một chức năng có thể xuất
hiện ở nhiều nơi, trong đó plan hoặc ghi chú lịch sử cũ đôi khi mâu thuẫn với code
và spec hiện hành. Agent có nguy cơ đọc nhầm nguồn, rồi sửa hành vi đúng thành sai.

Sản phẩm sẽ phát triển thêm nhiều loại hồ sơ nghiệp vụ, trước mắt gồm:

- Hồ sơ thừa kế.
- Hồ sơ chuyển nhượng.
- Hồ sơ tặng cho.
- Hồ sơ tách thửa.

Các loại hồ sơ có thể cùng sử dụng OCR, Stage/Pool, dữ liệu người/tài sản và sinh
Word, nhưng sở hữu quy tắc nghiệp vụ, vai trò, validation, workflow và placeholder
khác nhau.

## Động lực kiến trúc

1. Agent phải tìm được một nguồn sự thật rõ ràng cho mỗi nghiệp vụ.
2. Tài liệu dùng chung không được chứa business rule của một loại hồ sơ.
3. Thêm loại hồ sơ mới không làm nhân bản OCR, Stage/Pool hoặc Word engine.
4. `AGENTS.md` phải ngắn và chỉ đóng vai trò định tuyến.
5. Graphify chịu trách nhiệm mapping code; tài liệu không duy trì danh sách code
   chi tiết dễ stale.
6. Không tái cấu trúc runtime chỉ để làm cây thư mục trông đẹp hơn.

## Quyết định

Áp dụng modular monolith về mặt ranh giới tri thức, chia tài liệu thành ba nhóm:

```text
docs/
  README.md
  domains/
    inheritance/
    transfer/
    gift/
    parcel-split/
  platform/
    document-intake/
    case-workspace/
    document-generation/
    party-registry/
    property-registry/
  architecture/
    README.md
    decisions/
```

### Domain modules

Mỗi folder dưới `docs/domains/` là một bounded context nghiệp vụ. Module sở hữu:

- Thuật ngữ và vai trò nghiệp vụ.
- Business rule và invariant.
- Workflow và validation.
- UX riêng của loại hồ sơ.
- Cách ánh xạ OCR vào hồ sơ.
- Quy tắc sử dụng Stage/Pool.
- Placeholder và template nghiệp vụ.

Module không được sửa hoặc định nghĩa thay business rule của module khác.

### Platform capabilities

Mỗi folder dưới `docs/platform/` mô tả một capability dùng chung:

- `document-intake`: upload, file tạm, OCR provider và kết quả chuẩn hóa.
- `case-workspace`: cơ chế Stage, Pool, assignment và lưu trạng thái chung.
- `document-generation`: Word rendering và placeholder engine.
- `party-registry`: dữ liệu người dùng chung.
- `property-registry`: dữ liệu tài sản dùng chung.

Platform chỉ định nghĩa contract và cơ chế chung. Rule riêng của hồ sơ phải nằm
trong domain module và kết nối qua `integrations.md`.

Ví dụ: `document-intake` biết cách trích xuất CCCD; `inheritance` quyết định người
trên CCCD có vai trò gì và có được đưa vào Stage hay không.

### Cấu trúc bên trong module

Các file sau là tùy nhu cầu, không bắt buộc tạo đủ:

```text
<module>/
  README.md
  spec.md
  technical.md
  ux.md
  integrations.md
  plan.md
  decisions/
  research/
```

- `README.md`: cổng vào, trạng thái, phạm vi, thứ tự đọc và phần không thuộc module.
- `spec.md`: nguồn sự thật cho business rule và invariant.
- `technical.md`: contract, state và data flow kỹ thuật ổn định.
- `ux.md`: hành vi UI có thể quan sát được.
- `integrations.md`: cách domain sử dụng platform capability.
- `plan.md`: chỉ kế hoạch đang hoạt động; hoàn tất thì xóa.
- `decisions/`: quyết định quan trọng cần giữ lý do và hậu quả.
- `research/`: tài liệu tham khảo, luôn non-normative.

Không tạo `history.md` hoặc changelog dài để lặp lại Git history. Khi một quyết
định cũ vẫn cần giải thích, lưu ADR với trạng thái `Accepted`, `Superseded` hoặc
`Deprecated`.

## Thứ tự nguồn sự thật

```text
AGENTS.md hard rules
  -> accepted architecture decisions
  -> domain spec
  -> platform contract
  -> technical/UX docs
  -> active plan
  -> research
```

`spec.md` và `contract.md` là normative cho hành vi nghiệp vụ. ADR ở trạng thái
`Accepted` là normative cho kiến trúc, nhưng không được dùng thay business rule.
`plan.md`, ADR đã `Superseded`/`Deprecated` và `research/` là non-normative.

Nếu code và spec mâu thuẫn, agent phải báo conflict và xác minh trước khi sửa;
không tự đổi code hoặc spec theo suy đoán.

## Vai trò của AGENTS.md và Graphify

`AGENTS.md` chỉ giữ:

1. Hard rules toàn dự án.
2. Scope và verify protocol.
3. Bảng `Task area -> module README`.
4. Quy tắc dùng Graphify.
5. Quy tắc xử lý xung đột nguồn sự thật.

Graphify được dùng để tìm code, caller và impact. Tài liệu module chỉ nêu entry
point khi đó là contract ổn định; không liệt kê toàn bộ file/function runtime.

## Quy tắc tiến hóa code

Việc tổ chức lại tài liệu không tự động cho phép di chuyển code runtime.

Khi thêm domain module thứ hai, code mới nên được tổ chức theo module nghiệp vụ.
Chỉ trích OCR, Stage/Pool hoặc Word thành abstraction dùng chung sau khi có ít nhất
hai consumer thật chứng minh phần contract giống nhau. Không xây framework dựa
trên nhu cầu dự đoán.

Mỗi thay đổi runtime vẫn phải tuân thủ scope, routed spec và verification hiện có.

## Migration đã chốt

- Xóa `docs/word_template_properties_guide.md`; không merge vì Word/placeholder
  đang được thiết kế lại hoàn toàn.
- Không tạo `soul.md`; `AGENTS.md` là chỉ dẫn root duy nhất.
- Loại bỏ các kho ngang `plans/specs/issues/changelog/learning/superpowers` sau khi
  nội dung hiện hành đã được phân loại vào module tương ứng.
- Plan lịch sử không còn giá trị được xóa; quyết định còn giá trị được rút thành ADR.
- QR và Local OCR là thay đổi behavior riêng, không gộp vào migration tài liệu.
- Không di chuyển code runtime trong task dọn tài liệu.

## Phương án đã loại

### Chia theo loại tài liệu

Giữ `plans`, `specs`, `issues` và `research` ở cấp toàn repo. Phương án này làm
một chức năng bị rải qua nhiều nơi và duy trì lỗi hiện tại.

### Chỉ chia theo domain nghiệp vụ

Đặt toàn bộ OCR, Pool và Word trong từng loại hồ sơ. Phương án này dẫn tới nhân
bản capability dùng chung và tạo nhiều nguồn sự thật.

### Microservices ngay từ đầu

Không cần thiết ở quy mô hiện tại và làm tăng chi phí vận hành, giao tiếp và dữ
liệu phân tán trước khi ranh giới nghiệp vụ ổn định.

## Hậu quả

### Tích cực

- Agent đọc theo progressive disclosure thay vì nạp toàn bộ tài liệu.
- Business rule có owner và ranh giới rõ.
- Thêm loại hồ sơ mới không cần tạo thêm kho tài liệu ngang.
- Platform contract và domain rule không bị trộn lẫn.
- Có đường tiến hóa sang code module-first mà không buộc rewrite ngay.

### Chi phí

- Cần một lần phân loại, di chuyển và xóa tài liệu cũ.
- Link trong `AGENTS.md` và README module phải được kiểm tra khi đổi cấu trúc.
- Ranh giới domain/platform cần được giữ trong review và verification.

## Kiểm soát tối thiểu

Migration phải để lại một kiểm tra tự động, không thêm dependency, xác nhận:

- Mọi đường dẫn trong bảng routing của `AGENTS.md` tồn tại.
- Mọi module hiện hành có `README.md`.
- Không còn kho tài liệu ngang đã bị loại.
- Tài liệu normative và non-normative được phân biệt rõ.

## Nguồn tham khảo

- OpenAI, Harness engineering: https://openai.com/index/harness-engineering/
- Microsoft, Tactical DDD: https://learn.microsoft.com/en-ca/azure/architecture/microservices/model/tactical-ddd
- AWS, Decompose by subdomain: https://docs.aws.amazon.com/prescriptive-guidance/latest/modernization-decomposing-monoliths/decompose-subdomain.html
- Martin Fowler, Monolith First: https://martinfowler.com/bliki/MonolithFirst.html
- FastAPI, Bigger Applications: https://fastapi.tiangolo.com/tutorial/bigger-applications/
- Google Cloud, Architecture Decision Records: https://docs.cloud.google.com/architecture/architecture-decision-records
