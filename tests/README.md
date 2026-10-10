# 复测套件 (tests/)

> 本目录是**独立的开发期复测资产**，不参与技能运行：技能运行只需要 `SKILL.md`、`commands/`、`rules/` 与 `scripts/pai_pan.py`（+vendor）。技能分发打包时可整目录剔除，不影响功能。

## 文件清单

| 文件 | 用途 |
| :--- | :--- |
| `复测协议.md` | 复测方法论全文：可验证边界、行业标准（GB/T 33661-2017）、三层复测体系、王侯将相/名人用法、可重复验证性设计 |
| `名人案例.md` | 演示用命例（含帝王命例，三柱对拍权威表验证、时辰存疑规范） |
| `test_pai_pan.py` | 黄金用例回归：高危边界锚点 + 与独立实现（jinchenma94/bazi-skill，MIT）18 例交叉验证，秒级 |
| `test_authority.py` | 权威数据全量复测：1900-2052 节气 3,672 条、换柱边界 1,836 条、日柱 55,883 天、立春年界 153 条，约 40 秒，`--quick` 秒级快检 |
| `validate_citations.py` | 典籍卡片机械校验：ID 唯一、六字段齐备、层级枚举、竞合双向闭合、全文档引用 ID 存在性，秒级 |
| `testdata/` | 权威对照数据（中国历法公共数据集，Zenodo #22820072，CC BY 4.0，依 GB/T 33661-2017 用 JPL DE421 星历计算，与紫金山天文台官方值差 ≤30 秒），含许可证 |

## 操作手册

```bash
# 日常回归（每次改 scripts/pai_pan.py 或 rules/ 口径后）
python tests/test_pai_pan.py
python tests/validate_citations.py    # 改典籍卡片或引用后必跑

# 权威全量复测（发版前 / 引擎 vendor 升级 / 口径变更）
python tests/test_authority.py            # 约 40 秒
python tests/test_authority.py --quick    # 秒级快检

# 排盘演示 / 手工抽查
python scripts/pai_pan.py --year 1990 --month 5 --day 15 --hour 12:00 --sex 男
```

- L2 解读层稳定性：黄金盘（1990-05-15 12:00 男）完整解读 3 次，对照 `复测协议.md` 第三节基准定性表。
- L3 交付层合规：`../commands/50-交付前质量核验.md` 24 项清单逐条打勾。

**复测通过门槛**：L1 全部测试通过 + L2 黄金盘 5 项定性 3 次一致 + L3 清单零遗留。

## 口径变更纪律

排盘口径四处一体：`scripts/pai_pan.py` 头部锚点注释、`rules/1-排盘口径.md`、`rules/3-神煞规则.md`（神煞表）、`tests/test_pai_pan.py`（黄金用例）——改一处必须同步其余三处，任一测试失败即阻断。
