#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pai_pan.py 黄金用例回归测试。

覆盖全部高危边界：立春年柱分界、节气月柱分界、早晚子时、
大运顺逆、农历阳历同盘一致性、时辰未知六字盘、神煞查表、
十神口径与引擎一致性、旬空自检，以及与另一独立实现
（jinchenma94/bazi-skill 的 pai_pan.py，MIT）批量交叉验证。

运行：python scripts/test_pai_pan.py
"""

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent          # tests/
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import pai_pan  # noqa: E402

JINCHEN = Path(r"D:\IdeaWorkspace\.bazi-benchmarks\jinchen-bazi-skill\scripts\pai_pan.py")


def run(*args):
    r = subprocess.run([sys.executable, str(SCRIPTS / "pai_pan.py"), "--json", *args],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, f"排盘失败: {r.stderr}"
    return json.loads(r.stdout)


def pillars_of(chart):
    return "".join(chart["四柱"][p]["干支"] for p in ("年", "月", "日", "时") if p in chart["四柱"])


class TestGolden(unittest.TestCase):
    """黄金锚点：与脚本头部 docstring 及 rules/1-排盘口径.md 一一对应。"""

    def test_golden_1990_0515_noon_male(self):
        c = run("--year", "1990", "--month", "5", "--day", "15", "--hour", "12:00", "--sex", "男")
        self.assertEqual(pillars_of(c), "庚午辛巳庚辰壬午")

    def test_before_lichun_year_is_jisi(self):
        c = run("--year", "1990", "--month", "2", "--day", "3", "--hour", "10:00", "--sex", "男")
        self.assertEqual(c["四柱"]["年"]["干支"], "己巳")  # 立春 1990-02-04 10:14 之前

    def test_after_lichun_year_is_gengwu(self):
        c = run("--year", "1990", "--month", "2", "--day", "4", "--hour", "11:00", "--sex", "男")
        self.assertEqual(c["四柱"]["年"]["干支"], "庚午")

    def test_late_zi_uses_next_day_pillar(self):
        c = run("--year", "1990", "--month", "5", "--day", "15", "--hour", "23:30", "--sex", "男")
        self.assertEqual(pillars_of(c), "庚午辛巳辛巳戊子")  # 子平口径：日柱时柱按次日
        self.assertTrue(any("夜子时" in w for w in c["警告"]))

    def test_early_zi_keeps_same_day_pillar(self):
        c = run("--year", "1990", "--month", "5", "--day", "15", "--hour", "00:30", "--sex", "男")
        self.assertEqual(pillars_of(c), "庚午辛巳庚辰丙子")
        self.assertTrue(any("早子时" in w for w in c["警告"]))

    def test_yin_year_male_reverse_dayun(self):
        c = run("--year", "1991", "--month", "8", "--day", "15", "--hour", "10:00", "--sex", "男")
        self.assertEqual(pillars_of(c), "辛未丙申丁巳乙巳")
        d = c["大运"]
        self.assertEqual(d["方向"], "逆排")
        self.assertEqual(d["步骤"][0]["干支"], "乙未")  # 月柱丙申的上一柱

    def test_yin_year_female_forward_dayun(self):
        c = run("--year", "1991", "--month", "8", "--day", "15", "--hour", "10:00", "--sex", "女")
        d = c["大运"]
        self.assertEqual(d["方向"], "顺排")
        self.assertEqual(d["步骤"][0]["干支"], "丁酉")  # 月柱丙申的下一柱

    def test_yang_year_female_reverse_dayun(self):
        c = run("--year", "1990", "--month", "5", "--day", "15", "--hour", "12:00", "--sex", "女")
        d = c["大运"]
        self.assertEqual(d["方向"], "逆排")
        self.assertEqual(d["步骤"][0]["干支"], "庚辰")  # 月柱辛巳的上一柱

    def test_lunar_solar_same_chart(self):
        a = run("--year", "1990", "--month", "4", "--day", "21", "--calendar", "lunar",
                "--hour", "12:00", "--sex", "男")
        b = run("--year", "1990", "--month", "5", "--day", "15", "--hour", "12:00", "--sex", "男")
        self.assertEqual(pillars_of(a), pillars_of(b))
        self.assertEqual(pillars_of(a), "庚午辛巳庚辰壬午")

    def test_hour_unknown_six_chars(self):
        c = run("--year", "1990", "--month", "5", "--day", "15", "--sex", "男")
        self.assertEqual(pillars_of(c), "庚午辛巳庚辰")
        self.assertNotIn("时", c["四柱"])
        self.assertIsNone(c["大运"])
        self.assertTrue(any("时辰未知" in w for w in c["警告"]))

    def test_sex_unknown_no_dayun(self):
        c = run("--year", "1990", "--month", "5", "--day", "15", "--hour", "12:00")
        self.assertIsNone(c["大运"])
        self.assertTrue(any("性别未知" in w for w in c["警告"]))

    def test_xunkong_anchor(self):
        c = run("--year", "1990", "--month", "5", "--day", "15", "--hour", "12:00", "--sex", "男")
        self.assertEqual(c["日柱旬空"], "申酉")  # 庚辰在甲戌旬

    def test_skill_example_1995_0815(self):
        c = run("--year", "1995", "--month", "8", "--day", "15", "--hour", "14:30", "--sex", "男")
        self.assertEqual(len(pillars_of(c)), 8)  # 八字齐全，具体干支由交叉验证保证

    def test_lon_boundary_warning_no_pillar_change(self):
        c = run("--year", "1990", "--month", "5", "--day", "15", "--hour", "10:52", "--sex", "男",
                "--lon", "88.0")  # 乌鲁木齐经度，修正-128分钟，10:52→8:44 跨巳/辰边界
        self.assertTrue(any("真太阳时修正" in w for w in c["警告"]))
        self.assertTrue(any("经度(88.0-120)×4≈-128分钟" in w for w in c["警告"]))
        self.assertEqual(c["四柱"]["时"]["地支"], "巳")  # 不改柱，仍按钟表时间

    def test_lichun_boundary_direction_wording(self):
        # 2000-02-04 22:45 在立春 20:40 之后 → 年柱庚辰，警告须写"立春…后"
        c = run("--year", "2000", "--month", "2", "--day", "4", "--hour", "22:45", "--sex", "女")
        self.assertEqual(c["四柱"]["年"]["干支"], "庚辰")
        hit = [w for w in c["警告"] if "出生在立春" in w]
        self.assertTrue(hit and "后" in hit[0], f"方向词错误: {hit}")

    def test_shichen_midpoint_matches_hour(self):
        # 时辰名"午"中点=12:00，应与钟点输入同盘
        a = run("--year", "1990", "--month", "5", "--day", "15", "--shichen", "午", "--sex", "男")
        b = run("--year", "1990", "--month", "5", "--day", "15", "--hour", "12:00", "--sex", "男")
        self.assertEqual(pillars_of(a), pillars_of(b))
        self.assertEqual(pillars_of(a), "庚午辛巳庚辰壬午")
        self.assertTrue(any("时辰中点" in w for w in a["警告"]))

    def test_shichen_zi_early_zi_warning(self):
        c = run("--year", "1990", "--month", "5", "--day", "15", "--shichen", "子", "--sex", "男")
        self.assertEqual(c["四柱"]["日"]["干支"], "庚辰")  # 00:00 早子时 → 当日日柱
        self.assertTrue(any("早子时口径" in w for w in c["警告"]))
        self.assertTrue(any("23:00" in w for w in c["警告"]))  # 必须提示晚子时差异

    def test_shichen_hour_mutex(self):
        r = subprocess.run([sys.executable, str(SCRIPTS / "pai_pan.py"),
                            "--year", "1990", "--month", "5", "--day", "15",
                            "--hour", "12:00", "--shichen", "午"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 2)

    def test_deceased_year_truncates_liunian(self):
        c = run("--year", "1930", "--month", "9", "--day", "7", "--hour", "10:00", "--sex", "男",
                "--deceased-year", "2021", "--liunian", "2020,2021,2022")
        self.assertEqual([l.split("年")[0] for l in c["流年"]], ["2020", "2021"])
        self.assertTrue(any("已故" in w and "2022" in w for w in c["警告"]))


class TestShiShen(unittest.TestCase):
    """十神口径：本表 vs lunar 引擎逐干对照。"""

    def test_shi_shen_table_for_jia(self):
        expect = {"甲": "比肩", "乙": "劫财", "丙": "食神", "丁": "伤官", "戊": "偏财",
                  "己": "正财", "庚": "七杀", "辛": "正官", "壬": "偏印", "癸": "正印"}
        for gan, ss in expect.items():
            self.assertEqual(pai_pan.shi_shen("甲", gan), ss, f"甲日见{gan}")

    def test_shi_shen_matches_engine(self):
        c = run("--year", "1990", "--month", "5", "--day", "15", "--hour", "12:00", "--sex", "男")
        day_gan = c["四柱"]["日"]["天干"]
        for pos in ("年", "月", "时"):
            got = pai_pan.shi_shen(day_gan, c["四柱"][pos]["天干"])
            self.assertEqual(got, c["四柱"][pos]["天干十神"],
                             f"{pos}柱十神与引擎不一致")


class TestShenSha(unittest.TestCase):
    """神煞查表（rules/3-神煞规则.md 同表）。"""

    def test_tian_yi(self):
        hits = pai_pan.shen_sha("庚", {"年": "丑", "月": "寅", "日": "辰"})
        self.assertIn({"神煞": "天乙贵人", "柱位": "年支", "地支": "丑", "查法": "日干庚→丑未"}, hits)

    def test_lu_shen(self):
        hits = pai_pan.shen_sha("庚", {"年": "申", "月": "寅", "日": "辰"})
        self.assertTrue(any(h["神煞"] == "禄神" and h["地支"] == "申" for h in hits))

    def test_yang_ren(self):
        hits = pai_pan.shen_sha("甲", {"年": "子", "月": "卯", "日": "辰"})
        self.assertTrue(any(h["神煞"] == "羊刃" and h["地支"] == "卯" for h in hits))

    def test_tao_hua_by_day_zhi(self):
        hits = pai_pan.shen_sha("甲", {"年": "子", "月": "午", "日": "酉"})
        # 年支子（申子辰局）→ 桃花在酉，命中日支酉
        self.assertTrue(any(h["神煞"] == "桃花" and h["地支"] == "酉" for h in hits))

    def test_yi_ma(self):
        hits = pai_pan.shen_sha("甲", {"年": "子", "月": "午", "日": "寅"})
        # 年支子（申子辰局）→ 驿马在寅，命中日支寅
        self.assertTrue(any(h["神煞"] == "驿马" and h["地支"] == "寅" for h in hits))

    def test_kong_wang_six_xun(self):
        known = {"甲子": "戌亥", "甲戌": "申酉", "甲申": "午未",
                 "甲午": "辰巳", "甲辰": "寅卯", "甲寅": "子丑"}
        for gz, kw in known.items():
            self.assertEqual(pai_pan.kong_wang(gz), kw, gz)


class TestRelations(unittest.TestCase):
    def test_chong(self):
        rel = pai_pan.zhi_relations({"年": "子", "月": "午", "日": "卯", "时": "酉"})
        self.assertTrue(any("六冲" in r for r in rel))

    def test_san_he_full(self):
        rel = pai_pan.zhi_relations({"年": "申", "月": "子", "日": "辰", "时": "午"})
        self.assertTrue(any("三合局" in r and "全" in r for r in rel))

    def test_san_he_half_without_wang_not_reported(self):
        rel = pai_pan.zhi_relations({"年": "申", "月": "辰", "日": "巳", "时": "丑"})
        self.assertFalse(any("半合" in r for r in rel))  # 申辰无子、巳丑无酉（均无旺神）不报

    def test_zi_xing(self):
        rel = pai_pan.zhi_relations({"年": "辰", "月": "午", "日": "辰", "时": "子"})
        self.assertTrue(any("自刑" in r for r in rel))


@unittest.skipUnless(JINCHEN.exists(), "未找到 jinchen 参照实现，跳过交叉验证")
class TestCrossCheckJinchen(unittest.TestCase):
    """与另一独立实现（jinchen，MIT）批量对照四柱。两套独立算法一致即为强证据。"""

    CASES = [
        ("1985-03-12", "06:30", "男"), ("1988-11-02", "22:15", "女"),
        ("1990-05-15", "12:00", "男"), ("1991-08-15", "10:00", "男"),
        ("1993-06-20", "04:45", "女"), ("1995-08-15", "14:30", "男"),
        ("1997-01-31", "17:20", "女"), ("2000-02-04", "23:40", "男"),
        ("2001-10-08", "01:05", "女"), ("2003-12-21", "19:50", "男"),
        ("2005-06-06", "08:00", "女"), ("2008-08-08", "20:08", "男"),
        ("2010-04-14", "15:33", "女"), ("2012-09-30", "11:11", "男"),
        ("2015-02-19", "07:07", "女"), ("2018-07-07", "13:14", "男"),
        ("2020-01-25", "05:55", "女"), ("2024-02-10", "09:09", "男"),
    ]

    @staticmethod
    def jinchen_pillars(solar: str, hour: str, sex: str) -> str:
        r = subprocess.run([sys.executable, str(JINCHEN), "--solar", solar,
                            "--hour", hour, "--sex", sex],
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        m = re.search(r"## 四柱\n.*?\n.*?\n\| 天干 \| (\S) \| (\S) \| (\S) \| (\S) \|.*?\n"
                      r"\| 地支 \| (\S) \| (\S) \| (\S) \| (\S) \|", r.stdout)
        g = m.groups()
        return "".join(g[i] + g[i + 4] for i in range(4))

    def test_all_cases_agree(self):
        for solar, hour, sex in self.CASES:
            y, m, d = solar.split("-")
            ours = pillars_of(run("--year", y, "--month", m, "--day", d,
                                  "--hour", hour, "--sex", sex))
            theirs = self.jinchen_pillars(solar, hour, sex)
            self.assertEqual(ours, theirs, f"{solar} {hour} {sex}: 我方{ours} vs jinchen{theirs}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
