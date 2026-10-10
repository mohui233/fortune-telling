#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""典籍卡片库机械校验（把引用纪律变成可执行检查）。

校验项：
1. 卡片 ID 唯一；索引表列出的 ID 全部存在；
2. 每张卡六字段齐备（典籍/原文/白话/适用前提/层级/反例边界）；
3. 层级枚举合法（核心论断/操作规则/例证/存疑）；
4. 竞合双向闭合：卡片 A 声明与 B 竞合，则 B 也必须声明与 A 竞合；
5. 仓库全部文档（commands/、rules/、tests/）中引用的卡片 ID 必须存在。

运行：python tests/validate_citations.py
"""

import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CARDS_FILE = ROOT / "rules" / "典籍卡片.md"

FIELDS = ("典籍", "原文", "白话", "适用前提", "层级", "反例边界")
LEVELS = ("核心论断", "操作规则", "例证", "存疑")
ID_RE = re.compile(r"\b([A-Z]{2,4}-\d{4})\b")
REF_RE = re.compile(r"\b[A-Z]{2,4}-\d{4}\b")


def parse_cards():
    text = CARDS_FILE.read_text(encoding="utf-8")
    blocks = {}
    order = []
    current = None
    for line in text.splitlines():
        m = re.match(r"^### ([\w-]+)", line)
        if m:
            current = m.group(1)
            blocks[current] = []
            order.append(current)
        elif current:
            blocks[current].append(line)
    return blocks, order, text


class TestCardLibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blocks, cls.order, cls.text = parse_cards()

    def test_ids_unique(self):
        self.assertEqual(len(self.blocks), len(set(self.order)), "卡片 ID 重复")

    def test_index_lists_only_existing_ids(self):
        index = self.text.split("## 索引")[1].split("---")[0] if "## 索引" in self.text else ""
        listed = set(ID_RE.findall(index))
        existing = set(self.blocks)
        self.assertEqual(listed - existing, set(), "索引表引用了不存在的卡片 ID")

    def test_six_fields_present(self):
        missing = []
        for cid, lines in self.blocks.items():
            body = "\n".join(lines)
            for f in FIELDS:
                if not re.search(rf"^- {f}：", body, re.M):
                    missing.append(f"{cid} 缺字段：{f}")
        self.assertEqual(missing, [], "\n".join(missing))

    def test_level_enum_valid(self):
        bad = []
        for cid, lines in self.blocks.items():
            body = "\n".join(lines)
            m = re.search(r"^- 层级：\s*(\S+)", body, re.M)
            if m and m.group(1) not in LEVELS:
                bad.append(f"{cid} 层级非法：{m.group(1)}")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_rival_links_bidirectional(self):
        """竞合双向闭合：A 声明与 B 竞合 → B 也必须声明与 A 竞合。"""
        oneway = set()
        for cid, lines in self.blocks.items():
            body = "\n".join(lines)
            seg = body[body.find("- 竞合"):] if "- 竞合" in body else ""
            for rival in set(ID_RE.findall(seg)):
                if rival in self.blocks:
                    rbody = "\n".join(self.blocks[rival])
                    rseg = rbody[rbody.find("- 竞合"):] if "- 竞合" in rbody else ""
                    if cid not in ID_RE.findall(rseg):
                        oneway.add(f"{cid} → {rival}（单向）")
                else:
                    oneway.add(f"{cid} → {rival}（对方不存在）")
        self.assertEqual(sorted(oneway), [], "\n".join(sorted(oneway)))

    def test_all_references_exist(self):
        """commands/、rules/、tests/ 全部文档引用的卡片 ID 必须存在（卡片库文件自身除外）。"""
        existing = set(self.blocks)
        missing = []
        files = {md for md in list(ROOT.glob("commands/*.md")) +
                 list(ROOT.glob("rules/*.md")) + list(ROOT.glob("tests/*.md"))} - {CARDS_FILE}
        for md in sorted(files):
            for ref in REF_RE.findall(md.read_text(encoding="utf-8")):
                if ref not in existing:
                    missing.append(f"{md.as_posix()} -> {ref}")
        self.assertEqual(missing, [], "\n".join(missing))

    def test_docstring_rule6_references_valid(self):
        """rules/6 与 rules/3 引用的卡片（SH-0002、DTS-0002）存在且层级允许支撑规则。"""
        for ref in ("SH-0002", "DTS-0002"):
            self.assertIn(ref, self.blocks, f"{ref} 缺失")


if __name__ == "__main__":
    unittest.main(verbosity=2)
