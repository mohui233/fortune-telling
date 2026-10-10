#!/usr/bin/env bash
# 技能复测门禁：任何改动提交前运行，任一步失败即退出非零。
# 用法：bash scripts/verify.sh        # 日常门禁（快检，秒级）
#       bash scripts/verify.sh --full # 发版门禁（含权威数据全量对照，约 40 秒）
set -e
cd "$(dirname "$0")/.."

echo "=== ① 黄金用例回归（含跨实现交叉验证） ==="
python tests/test_pai_pan.py

echo ""
echo "=== ② 典籍卡片机械校验 ==="
python tests/validate_citations.py

echo ""
echo "=== ③ 权威数据对照 ==="
if [ "$1" = "--full" ]; then
  python tests/test_authority.py
else
  python tests/test_authority.py --quick
fi

echo ""
echo "=== ④ 文档交叉引用与卡片 ID 校验 ==="
python - <<'EOF'
import re, sys, pathlib
root = pathlib.Path(".")
errs = []

# 4.1 文档内引用的文件路径必须存在
for md in list(root.glob("*.md")) + list(root.glob("commands/*.md")) + \
          list(root.glob("rules/*.md")) + list(root.glob("tests/*.md")):
    text = md.read_text(encoding="utf-8")
    for ref in set(re.findall(r"`((?:rules|commands|scripts|tests)/[^`]+?)`", text)):
        ref = ref.split(":")[0]
        if not (root / ref).exists():
            errs.append(f"{md.as_posix()} 引用了不存在的文件: {ref}")

# 4.2 文档引用的典籍卡片 ID 必须存在
cards = set(re.findall(r"### ([A-Za-z]+-\d+)", (root / "rules/典籍卡片.md").read_text(encoding="utf-8")))
card_file = root / "rules/典籍卡片.md"
for md in list(root.glob("commands/*.md")) + list(root.glob("rules/*.md")) + \
          list(root.glob("tests/*.md")) + list(root.glob("*.md")):
    if md == card_file:
        continue
    for ref in re.findall(r"\b[A-Z]{2,4}-\d{4}\b", md.read_text(encoding="utf-8")):
        if ref not in cards:
            errs.append(f"{md.as_posix()} 引用了不存在的卡片 ID: {ref}")

if errs:
    print("发现", len(errs), "个问题:")
    for e in errs:
        print(" -", e)
    sys.exit(1)
print("引用校验通过")
EOF

echo ""
echo "verify 全部通过 ✅"
