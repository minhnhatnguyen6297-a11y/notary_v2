# Skill: model-router

Kích hoạt khi: user yêu cầu `/check-model-quota` hoặc cần route task mới.

## Config
Đọc `.agents/model-budget.json` để lấy tier, quota, routing rules.

## Flow

### 1. Check quota (khi user yêu cầu `/check-model-quota`)
- Hướng dẫn user check tại https://opencode.ai/auth
- User cung cấp số liệu → cập nhật `personal_remaining_5h` / `personal_remaining_month` trong config
- Model còn <30% quota → warning, <5% → critical
- In bảng tóm tắt

### 2. Route task (khi nhận task mới)
- Đọc `task_routing` trong config → xác định tier + primary model
- Check `personal_remaining_5h` của primary:
  - >30% → dùng primary
  - 5-30% → warn + đề xuất fallback cùng tier
  - <5% → auto chuyển fallback 1
- In routing decision 1 dòng

### 3. Auto-reclassify (khi có model mới từ OpenCode)
- Fetch https://opencode.ai/zen/go/v1/models
- So sánh với config → đề xuất xếp tier
- User duyệt → cập nhật config

## Rules
- OCR task → luôn Tier S
- Planning → luôn Tier S
- Auto fallback trong cùng tier, không hỏi
- Xuống tier thấp hơn → phải hỏi user
- Không tự chạy khi bắt đầu task — chỉ load khi user yêu cầu hoặc task cần routing
