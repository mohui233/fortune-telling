#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""四柱八字确定性排盘 CLI（本技能唯一排盘事实源）。

引擎：vendor/lunar_python（6tail lunar-python，MIT，业内事实标准）。
计算口径由本文件固定，任何解读不得覆盖脚本输出。

算法与口径锚点（QA 对照，与 rules/1-排盘口径.md 一致）
-----------------------------------------------------
1. 时区：一律北京时间 UTC+8，不用本机时区。
2. 晚子时（子平口径，sect=1）：23:00 起日柱、时柱均按次日计算（标记"夜子时"）；
   00:00-01:00 为早子时，日柱用当日，时柱按当日日干五鼠遁。
   锚点：1990-05-15 12:00 = 庚午/辛巳/庚辰/壬午；23:30 = 庚午/辛巳/辛巳/戊子；
   00:30 = 庚午/辛巳/庚辰/丙子。
3. 年柱以立春精确时刻分界（非正月初一、非 2 月 4 日零点）。
   锚点：1990-02-03 10:00 年柱己巳；1990-02-04 11:00（立春 10:14 后）年柱庚午。
4. 月柱以十二「节」（立春/惊蛰/清明/立夏/芒种/小暑/立秋/白露/寒露/立冬/大雪/小寒）
   精确时刻分界，中气不换月。
5. 大运：年干阳(甲丙戊庚壬)男/年干阴(乙丁己辛癸)女 → 顺排，反之逆排；
   从月柱下一柱（顺）或上一柱（逆）起，不把月柱当第一步。
   锚点：1991-08-15 男（辛未阴年）逆排，首步乙未。
6. 起运岁数由引擎按「出生到节气天数 ÷ 3」精算（年/月一并输出，虚岁标注）。
7. 十神、藏干、纳音、旬空、节气时刻：直接取引擎结果，本脚本不自算。
8. 神煞、刑冲合害：本脚本内建表，与 rules/3-神煞规则.md 为同一张表（唯一口径）。
   时柱未知时不参与神煞与地支关系，且不排大运。

真太阳时：默认钟表时间（档位0）。--lon 给出出生地经度时（档位1），
只做 (经度-120)×4 分钟的边界警示，不改柱；钟表时间距时辰整点边界
≤15 分钟或经度修正后跨时辰 → 输出警告，请用户确认。

用法：
  python pai_pan.py --year 1990 --month 5 --day 15 --hour 12:00 --sex 男
  python pai_pan.py --year 1990 --month 4 --day 21 --calendar lunar --hour 12:00 --sex male
  python pai_pan.py --year 1995 --month 8 --day 15 --hour 14:30 --sex 女 --lon 113.5 --json
  python pai_pan.py --year 1990 --month 5 --day 15   # 时辰未知 → 六字盘 + 警告

输出：markdown 文本（默认）或 JSON（--json）到 stdout；输入错误走 stderr，退出码 2。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))
from lunar_python import Solar, Lunar  # noqa: E402

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
SHICHEN = list(ZHI)

# ---- 神煞表（与 rules/3-神煞规则.md 同一张表，改表须两处同步）----
TIAN_YI = {  # 天乙贵人：按日干查地支
    "甲": "丑未", "戊": "丑未", "庚": "丑未",
    "乙": "子申", "己": "子申",
    "丙": "亥酉", "丁": "亥酉",
    "壬": "卯巳", "癸": "卯巳", "辛": "午寅",
}
WEN_CHANG = dict(zip(GAN, "巳午申酉申酉亥子寅卯"))      # 文昌贵人：按日干
LU_SHEN = dict(zip(GAN, "寅卯巳午巳午申酉亥子"))          # 禄神（临官）：按日干
YANG_REN = dict(zip(GAN, "卯寅午巳午巳酉申子亥"))         # 羊刃（帝旺，阴阳逆行论）：按日干
SAN_HE = {  # 三合局 →（将星, 驿马, 桃花, 华盖）：按年支或日支起查
    "申子辰": ("子", "寅", "酉", "辰"),
    "寅午戌": ("午", "申", "卯", "戌"),
    "巳酉丑": ("酉", "亥", "午", "丑"),
    "亥卯未": ("卯", "巳", "子", "未"),
}
SAN_HE_STAR_NAMES = ("将星", "驿马", "桃花", "华盖")

CHONG = {"子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥"}                  # 六冲
LIUHE = {"子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未"}                  # 六合
HAI = {"子未", "丑午", "寅巳", "卯辰", "申亥", "酉戌"}                    # 六害
XING_PAIRS = {"寅巳", "巳申", "寅申", "丑戌", "戌未", "丑未", "子卯"}      # 相刑（两两）
ZI_XING = set("辰午酉亥")                                                 # 自刑
SAN_HUI = {"寅卯辰": "木", "巳午未": "火", "申酉戌": "金", "亥子丑": "水"}  # 三会
GAN_HE = {"甲己", "乙庚", "丙辛", "丁壬", "戊癸"}                          # 天干五合


def shi_shen(day_gan: str, other_gan: str) -> str:
    """十神（日柱天干十神在排盘时直接标"日主"，此处同干返回比肩）。
    与引擎同口径，用于流年/大运天干。"""
    d, o = GAN.index(day_gan), GAN.index(other_gan)
    same_yin_yang = (d % 2) == (o % 2)
    wx_d, wx_o = d // 2, o // 2          # 天干五行：甲乙0木 丙丁1火 戊己2土 庚辛3金 壬癸4水
    if wx_d == wx_o:                  # 同五行 → 比劫
        return "比肩" if same_yin_yang else "劫财"
    if (wx_d + 1) % 5 == wx_o:        # 我生 → 食伤
        return "食神" if same_yin_yang else "伤官"
    if wx_o == (wx_d + 2) % 5:        # 我克 → 财
        return "偏财" if same_yin_yang else "正财"
    if (wx_o + 1) % 5 == wx_d:        # 生我 → 印
        return "偏印" if same_yin_yang else "正印"
    return "七杀" if same_yin_yang else "正官"  # 克我 → 官杀


def find_san_he_group(zhi: str) -> str | None:
    return next((g for g in SAN_HE if zhi in g), None)


def shen_sha(day_gan: str, branches: dict) -> list[dict]:
    """按 rules/3-神煞规则.md 查命局神煞。branches: {柱位: 地支}（时柱未知则不含时）。"""
    hits = []

    def scan(star: str, targets: str, basis: str):
        for pos, zhi in branches.items():
            if zhi in targets:
                hits.append({"神煞": star, "柱位": pos + "支", "地支": zhi, "查法": basis})

    scan("天乙贵人", TIAN_YI.get(day_gan, ""), f"日干{day_gan}→{TIAN_YI.get(day_gan, '')}")
    scan("文昌贵人", WEN_CHANG.get(day_gan, ""), f"日干{day_gan}→{WEN_CHANG.get(day_gan, '')}")
    scan("禄神", LU_SHEN.get(day_gan, ""), f"日干{day_gan}→{LU_SHEN.get(day_gan, '')}")
    scan("羊刃", YANG_REN.get(day_gan, ""), f"日干{day_gan}→{YANG_REN.get(day_gan, '')}")

    for pos, zhi in branches.items():  # 将星/驿马/桃花/华盖按年支与日支起查
        if pos not in ("年", "日"):
            continue
        group = find_san_he_group(zhi)
        if not group:
            continue
        for name, target in zip(SAN_HE_STAR_NAMES, SAN_HE[group]):
            for p, z in branches.items():
                if z == target:
                    hits.append({"神煞": name, "柱位": p + "支", "地支": z,
                                 "查法": f"{pos}支{zhi}（{group}局）→{target}"})
    uniq = {(h["神煞"], h["柱位"], h["地支"]): h for h in hits}
    return sorted(uniq.values(), key=lambda h: h["柱位"])


def kong_wang(day_gz: str) -> str:
    """日柱旬空：甲子旬空戌亥、甲戌旬空申酉……"""
    day_idx = next(i for i in range(60) if GAN[i % 10] + ZHI[i % 12] == day_gz)
    xun_start = day_idx - (day_idx % 10)
    return ZHI[(xun_start + 10) % 12] + ZHI[(xun_start + 11) % 12]


def zhi_relations(branches: dict) -> list[str]:
    """四支（时柱未知则三支）之间的刑冲合害 + 三合三会。"""
    items = list(branches.items())
    out, seen = [], set()
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (p1, z1), (p2, z2) = items[i], items[j]
            pair = "".join(sorted(z1 + z2))
            for name, table in (("六冲", CHONG), ("六合", LIUHE),
                                ("六害", HAI), ("相刑", XING_PAIRS)):
                if pair in table and (name, pair) not in seen:
                    out.append(f"{p1}支{z1} — {p2}支{z2}：{name}")
                    seen.add((name, pair))
            if z1 == z2 and z1 in ZI_XING and ("自刑", z1 + z2) not in seen:
                out.append(f"{p1}支{z1} — {p2}支{z2}：自刑")
                seen.add(("自刑", z1 + z2))
    zhis = set(branches.values())
    for group, wx in SAN_HUI.items():
        if zhis >= set(group):
            where = "、".join(p for p, z in branches.items() if z in group)
            out.append(f"三会{wx}局（{group}）：见诸{where}")
    for group in SAN_HE:
        got = zhis & set(group)
        wang = SAN_HE[group][0]
        if len(got) == 3:
            out.append(f"三合局：{group}全（力量极大）")
        elif len(got) == 2 and wang in got:
            missing = (set(group) - got).pop()
            out.append(f"半合：{''.join(sorted(got, key=group.index))}（缺{missing}，合力减半）")
    return out


def gan_relations(stems: dict) -> list[str]:
    out = []
    items = list(stems.items())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            (p1, g1), (p2, g2) = items[i], items[j]
            if "".join(sorted(g1 + g2)) in GAN_HE:
                out.append(f"{p1}干{g1} — {p2}干{g2}：天干五合（合而不化，需月令与全局佐断）")
    return out


def year_gz_of(year: int) -> str:
    idx = (year - 4) % 60
    return GAN[idx % 10] + ZHI[idx % 12]


def gan_ke(a: str, b: str) -> bool:
    """天干五行相克（任一方向）。"""
    return (GAN.index(a) // 2 + 2) % 5 == GAN.index(b) // 2


def liu_nian(year: int, day_gan: str, day_gz: str, branches: dict, da_yun: list[dict]) -> str:
    gz = year_gz_of(year)
    parts = [f"{year}年 {gz}（{shi_shen(day_gan, gz[0])}）"]
    rel = []
    for p, b in branches.items():
        pair = "".join(sorted(gz[1] + b))
        for name, table in (("冲", CHONG), ("合", LIUHE), ("害", HAI), ("刑", XING_PAIRS)):
            if pair in table:
                rel.append(f"{name}{p}支")
    if rel:
        parts.append("关系：" + "、".join(rel))
    for step in da_yun:
        if step["起"] <= year <= step["止"] and step["干支"] == gz:
            parts.append("⚠ 岁运并临（与所行大运干支相同，力量加倍）")
            break
    if (gan_ke(gz[0], day_gz[0]) or gan_ke(day_gz[0], gz[0])) \
            and "".join(sorted(gz[1] + day_gz[1])) in CHONG:
        parts.append("⚠ 与日柱天克地冲（重大变动年）")
    return "；".join(parts)


def parse_hour(text: str) -> tuple[int, int]:
    t = text.strip().replace("：", ":")
    if ":" in t:
        h, m = t.split(":", 1)
        return int(h), int(m)
    if len(t) <= 2:
        return int(t), 0
    return int(t[:-2]), int(t[-2:])


def fmt_minutes(mins: float) -> str:
    return f"{mins:.0f}分钟" if mins < 60 else f"{mins / 60:.1f}小时"


def solar_dt(sw) -> datetime:
    return datetime(sw.getYear(), sw.getMonth(), sw.getDay(),
                    sw.getHour(), sw.getMinute(), sw.getSecond())


def equation_of_time_minutes(dt: datetime) -> float:
    """均时差近似（分钟，NOAA 近似式，全年约 -14~+16 分钟）。仅用于真太阳时量化警示。"""
    n = dt.timetuple().tm_yday
    B = 2 * math.pi * (n - 81) / 365.0
    return 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)


def build_chart(args) -> dict:
    if args.shichen:  # 时辰名 → 时辰中点（子时=00:00，早子时口径）
        idx = SHICHEN.index(args.shichen)
        hour = ((idx * 2) % 24, 0)
    else:
        hour = parse_hour(args.hour) if args.hour else None
    has_time = hour is not None
    warnings = []

    if args.calendar == "lunar":
        m = -args.month if args.leap else args.month
        lunar = (Lunar.fromYmdHms(args.year, m, args.day, hour[0], hour[1], 0) if has_time
                 else Lunar.fromYmd(args.year, m, args.day))
        solar = lunar.getSolar()
    else:
        solar = (Solar.fromYmdHms(args.year, args.month, args.day, hour[0], hour[1], 0) if has_time
                 else Solar.fromYmd(args.year, args.month, args.day))
        lunar = solar.getLunar()

    birth = datetime(solar.getYear(), solar.getMonth(), solar.getDay(),
                     *(hour if has_time else (12, 0)))
    if args.calendar == "lunar":
        warnings.append(f"农历输入已换算公历：{solar.toYmd()}（以公历节气时刻为准）")

    ec = lunar.getEightChar()
    ec.setSect(1)  # 子平口径：晚子时日柱按次日

    pillars = {}
    for pos, gz, hide, ss_gan, ss_zhi, nayin in (
        ("年", ec.getYear(), ec.getYearHideGan(), ec.getYearShiShenGan(),
         ec.getYearShiShenZhi(), ec.getYearNaYin()),
        ("月", ec.getMonth(), ec.getMonthHideGan(), ec.getMonthShiShenGan(),
         ec.getMonthShiShenZhi(), ec.getMonthNaYin()),
        ("日", ec.getDay(), ec.getDayHideGan(), "日主", ec.getDayShiShenZhi(), ec.getDayNaYin()),
    ):
        pillars[pos] = {"干支": gz, "天干": gz[0], "地支": gz[1], "藏干": hide,
                        "天干十神": ss_gan, "藏干十神": ss_zhi, "纳音": nayin}
    if has_time:
        gz = ec.getTime()
        pillars["时"] = {"干支": gz, "天干": gz[0], "地支": gz[1], "藏干": ec.getTimeHideGan(),
                        "天干十神": ec.getTimeShiShenGan(), "藏干十神": ec.getTimeShiShenZhi(),
                        "纳音": ec.getTimeNaYin()}
    else:
        warnings.append("时辰未知：时柱不排（六字盘），神煞与地支关系不含时柱，大运不排。")

    branches = {p: d["地支"] for p, d in pillars.items()}
    stems = {p: d["天干"] for p, d in pillars.items()}
    day_gz = pillars["日"]["干支"]
    day_gan = pillars["日"]["天干"]

    kw = ec.getDayXunKong()
    assert kw == kong_wang(day_gz), f"旬空自检失败: {kw} != {kong_wang(day_gz)}"

    shensha = shen_sha(day_gan, branches)
    zhi_rel = zhi_relations(branches)
    gan_rel = gan_relations(stems)

    # ---- 节气/立春边界 ----
    jieqi_lines = []
    n, p = lunar.getNextJie(), lunar.getPrevJie()
    for label, j in (("上一节", p), ("下一节", n)):
        d = (solar_dt(j.getSolar()) - birth).total_seconds() / 60
        jieqi_lines.append(
            f"{label}：{j.getName()} {j.getSolar().toYmdHms()}（{fmt_minutes(abs(d))}{'前' if d < 0 else '后'}）")
        if abs(d) <= 120:
            warnings.append(f"⚠ 距月柱节气边界（{j.getName()}）仅{fmt_minutes(abs(d))}，"
                            f"月柱以脚本结果 {pillars['月']['干支']} 为准，建议与专业排盘工具复核。")
        elif abs(d) <= 1440:
            warnings.append(f"距节气交界（{j.getName()}）24小时内（{fmt_minutes(abs(d))}），"
                            f"如出生时间记忆有偏差可能换月柱，当前按 {pillars['月']['干支']} 论。")
    lichun = lunar.getJieQiTable().get("立春")
    if lichun is not None:
        d = (solar_dt(lichun) - birth).total_seconds() / 60
        if abs(d) <= 1440:
            side = "前" if d >= 0 else "后"  # d>=0：立春在出生之后 → 出生在立春前
            warnings.append(f"⚠ 出生在立春（{lichun.toYmdHms()}）{side}{fmt_minutes(abs(d))}，"
                            f"年柱以脚本结果 {pillars['年']['干支']} 为准（立春分界，非正月初一）。")

    # ---- 时辰边界 / 真太阳时警示（只警示不改柱）----
    if has_time:
        h, mi = hour
        zhi_idx = ((h + 1) // 2) % 12
        cur = h * 60 + mi
        boundaries = [((2 * k + 23) % 24) * 60 for k in range(12)]  # 23,1,3,...,21 点
        dist = min(min(abs(cur - b), 1440 - abs(cur - b)) for b in boundaries)
        if args.shichen:
            if args.shichen == "子":
                warnings.append(f"仅提供时辰名（子），按 00:00 计算（早子时口径，日柱用当日 {pillars['日']['干支']}）。"
                                f"子时跨日界：若实际生于 23:00 后，日柱时柱将不同，建议确认具体钟点。")
            else:
                warnings.append(f"仅提供时辰名（{args.shichen}），按 {h:02d}:00（时辰中点）计算，"
                                f"时柱结论可能随实际钟点移动，建议确认具体钟点。")
        if dist <= 15:
            warnings.append(f"⚠ 出生时间距时辰整点边界仅{dist:.0f}分钟，钟表误差或真太阳时修正可能跨时辰，"
                            f"当前时柱按 {pillars['时']['干支']} 论，建议与用户确认。")
        if h >= 23:
            warnings.append(f"夜子时（{h:02d}:{mi:02d}）：按子平口径日柱、时柱均以次日"
                            f"（{pillars['日']['干支']}日）起算。")
        elif h == 0:
            warnings.append(f"早子时（{h:02d}:{mi:02d}）：日柱用当日 {pillars['日']['干支']}，"
                            f"时柱按当日日干五鼠遁。")
        if args.lon is not None:
            delta_lon = (args.lon - 120.0) * 4.0
            eot = equation_of_time_minutes(birth)
            total = delta_lon + eot
            zhi_shift = ((((cur + int(round(total))) // 60 + 1) // 2) % 12)
            if zhi_shift != zhi_idx:
                warnings.append(f"⚠ 真太阳时修正：经度({args.lon}-120)×4≈{delta_lon:+.0f}分钟、"
                                f"均时差≈{eot:+.0f}分钟，合计{total:+.0f}分钟；修正后时支由"
                                f"{SHICHEN[zhi_idx]}变为{SHICHEN[zhi_shift]}。"
                                f"脚本默认钟表时间不改柱，请用户确认采用哪一口径；"
                                f"确认修正后请以「用户已确认排盘」通道提供四柱。")
            elif dist <= 15:
                warnings.append(f"真太阳时修正：经度({args.lon}-120)×4≈{delta_lon:+.0f}分钟、"
                                f"均时差≈{eot:+.0f}分钟，合计{total:+.0f}分钟（未跨时支，仍按钟表时间论）。")

    # ---- 大运（性别与时辰缺一不可）----
    da_yun_rows, da_yun_info = [], None
    if args.sex and has_time:
        code = 1 if args.sex in ("男", "male", "m", "1") else -1
        yun = ec.getYun(code)
        male = code == 1
        yang_year = GAN.index(pillars["年"]["天干"]) % 2 == 0
        direction = "顺排" if yang_year == male else "逆排"
        da_yun_info = {
            "方向": direction,
            "依据": f"{'阳' if yang_year else '阴'}年{'男' if male else '女'}命 → {direction}",
            "起运": f"{yun.getStartYear()}年{yun.getStartMonth()}个月",
            "起运前": "以月柱论小运",
            "步骤": [{"干支": s.getGanZhi(), "起": s.getStartYear(), "止": s.getEndYear(),
                      "虚岁起": s.getStartAge(),
                      "十神": shi_shen(day_gan, s.getGanZhi()[0])}
                     for s in yun.getDaYun()[1:args.steps + 1]],
        }
        da_yun_rows = da_yun_info["步骤"]
    elif not args.sex:
        warnings.append("性别未知：大运顺逆与起运无法排，仅输出命局本体。")

    liunian_lines = []
    if args.liunian and da_yun_rows:
        years = args.liunian
        if args.deceased_year is not None:
            kept = [y for y in years if y <= args.deceased_year]
            if kept != years:
                warnings.append(f"命主已故（{args.deceased_year}年）：流年仅列至去世年份，"
                                f"{', '.join(map(str, sorted(set(years) - set(kept))))} 年已剔除。")
            years = kept
        liunian_lines = [liu_nian(y, day_gan, day_gz, branches, da_yun_rows) for y in years]

    return {
        "输入": {"公历": solar.toYmd() + (f" {hour[0]:02d}:{hour[1]:02d}" if has_time else "（时辰未知）"),
                 "农历": lunar.toString() if args.calendar == "solar" else
                     f"{'闰' if args.leap else ''}{args.month}月{args.day}日（用户输入，换算 {solar.toYmd()}）",
                 "性别": args.sex or "未知", "历法": args.calendar,
                 "时辰": (f"钟点 {hour[0]:02d}:{hour[1]:02d}" if args.hour else
                          (f"时辰名 {args.shichen}（按中点计算）" if args.shichen else "未知")),
                 "已故年份": args.deceased_year,
                 "经度": args.lon if args.lon is not None else "未提供（钟表时间）"},
        "四柱": pillars,
        "日柱旬空": kw,
        "神煞": shensha,
        "地支关系": zhi_rel,
        "天干关系": gan_rel,
        "大运": da_yun_info,
        "流年": liunian_lines,
        "节气": jieqi_lines,
        "警告": warnings,
    }


def render_markdown(c: dict) -> str:
    L = []
    i = c["输入"]
    L += ["## 输入",
          f"- 公历：{i['公历']}；农历：{i['农历']}",
          f"- 性别：{i['性别']}；历法：{i['历法']}；时辰：{i['时辰']}；经度：{i['经度']}"]
    if i["已故年份"] is not None:
        L.append(f"- 已故年份：{i['已故年份']}（流年仅列至该年）")
    L += ["", "## 四柱",
          "| 柱 | 干支 | 天干十神 | 藏干（十神） | 纳音 |",
          "| :--- | :--- | :--- | :--- | :--- |"]
    for pos in ("年", "月", "日", "时"):
        if pos not in c["四柱"]:
            L.append(f"| {pos} | 未知 | — | — | — |")
            continue
        p = c["四柱"][pos]
        hide = "、".join(f"{g}({s})" for g, s in zip(p["藏干"], p["藏干十神"]))
        L.append(f"| {pos} | {p['干支']} | {p['天干十神']} | {hide} | {p['纳音']} |")
    L.append(f"\n日柱旬空：**{c['日柱旬空']}**")
    L += ["", "## 神煞（与 rules/3-神煞规则.md 同一口径）"]
    if c["神煞"]:
        L += [f"- **{s['神煞']}**：{s['柱位']}（{s['地支']}）— 查法：{s['查法']}" for s in c["神煞"]]
    else:
        L.append("- 命局未见表内神煞。")
    L += ["", "## 刑冲合害"]
    rels = c["地支关系"] + c["天干关系"]
    L += [f"- {r}" for r in rels] if rels else ["- 四柱干支间无表内刑冲合害。"]
    L += ["", "## 大运"]
    d = c["大运"]
    if d:
        L.append(f"- 方向：**{d['方向']}**（{d['依据']}）；出生后 {d['起运']} 起运；{d['起运前']}。")
        L += ["| 步 | 干支 | 十神 | 起止年份 | 虚岁 |",
              "| :--- | :--- | :--- | :--- | :--- |"]
        L += [f"| {n} | {r['干支']} | {r['十神']} | {r['起']}-{r['止']} | {r['虚岁起']}起 |"
              for n, r in enumerate(d["步骤"], 1)]
    else:
        L.append("- 未排（性别或时辰未知）。")
    if c["流年"]:
        L += ["", "## 流年要点"] + [f"- {line}" for line in c["流年"]]
    L += ["", "## 节气边界"]
    L += [f"- {line}" for line in c["节气"]] if c["节气"] else ["- —"]
    L += ["", "## 警告"]
    L += [f"- {w}" for w in c["警告"]] if c["警告"] else ["- 无（排盘距各边界均有余量）。"]
    L.append("\n> 排盘口径：北京时间；立春分年、十二节分月、晚子时按子平口径（日柱时柱用次日）。"
             "本脚本是本技能唯一排盘事实源，解读不得覆盖。")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="四柱八字确定性排盘（唯一事实源）")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--month", type=int, required=True)
    ap.add_argument("--day", type=int, required=True)
    ap.add_argument("--hour", help="出生钟表时间 HH:MM（与 --shichen 互斥；缺省=时辰未知，六字盘）")
    ap.add_argument("--shichen", choices=list(ZHI), help="出生时辰名（子丑寅…，与 --hour 互斥；按时辰中点计算）")
    ap.add_argument("--sex", help="男/女（缺省=不排大运）")
    ap.add_argument("--calendar", default="solar", choices=["solar", "lunar"],
                    help="输入历法：solar 公历（默认）/ lunar 农历")
    ap.add_argument("--leap", action="store_true", help="农历输入且该月为闰月")
    ap.add_argument("--lon", type=float, default=None,
                    help="出生地东经经度（仅作真太阳时量化警示，不改柱）")
    ap.add_argument("--steps", type=int, default=9, help="输出大运步数（默认9）")
    ap.add_argument("--liunian", help="逗号分隔的流年年份，如 2025,2026")
    ap.add_argument("--deceased-year", type=int, default=None,
                    help="命主去世年份（流年仅列至该年）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    try:
        if args.hour and args.shichen:
            raise ValueError("--hour 与 --shichen 互斥")
        if not (1 <= args.month <= 12):
            raise ValueError(f"月份越界: {args.month}")
        if not (1 <= args.day <= (30 if args.calendar == "lunar" else 31)):
            raise ValueError(f"日期越界: {args.day}")
        if args.hour:
            h, m = parse_hour(args.hour)
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError(f"时间越界: {args.hour}")
        if args.liunian:
            args.liunian = [int(x) for x in args.liunian.split(",") if x.strip()]
        chart = build_chart(args)
    except Exception as e:
        print(f"[pai_pan] 输入错误：{e}", file=sys.stderr)
        return 2

    print(json.dumps(chart, ensure_ascii=False, indent=2) if args.json else render_markdown(chart))
    return 0


if __name__ == "__main__":
    sys.exit(main())
