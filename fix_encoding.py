"""
Fix double-encoding trong form.html.
Codex encode các ký tự tiếng Việt lần 2 qua CP1252, tạo ra mojibake.
Fix: encode CP1252 -> decode UTF-8 cho từng dòng bị ảnh hưởng.
"""
import sys, re
sys.stdout.reconfigure(encoding='utf-8')

path = r'D:\notary_v2\frontend\templates\cases\form.html'

# Pattern nhận biết dòng bị double-encode:
# Các ký tự Latin supplement (U+0080–U+00FF) hoặc một số ký tự CP1252 đặc biệt
# thường đi kèm nhau theo pattern mojibake
MOJIBAKE_PATTERN = re.compile(
    r'[\xc0-\xff][\x80-\xbf]|'         # Ä, á, â... theo sau bởi », ‹, ‰...
    r'[\u2018-\u201e\u2039\u203a]|'     # smart quotes / angle quotes từ CP1252
    r'[\u2022\u2026\u2013\u2014]'       # bullet, ellipsis, dashes từ CP1252
)

with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

fixed_lines = []
count = 0
for line in lines:
    if MOJIBAKE_PATTERN.search(line):
        try:
            fixed = line.encode('cp1252').decode('utf-8')
            if fixed != line:
                fixed_lines.append(fixed)
                count += 1
                continue
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    fixed_lines.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print(f'Fixed {count} lines')
