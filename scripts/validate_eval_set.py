#!/usr/bin/env python3
"""eval_set_v0 三重校验脚本 (P6-13-B2)

校验一: 用现有 loader 解析全部夹具,字段不齐报错
校验二: anchors.yaml 每条 canonical 确实出现在对应 sub-md 中
校验三: composite 的 members 引用的 id 全部存在
"""
import re
import sys
from pathlib import Path

import yaml

EVAL_DIR = Path(__file__).resolve().parents[1] / "eval_set_v0"


def normalize(text: str) -> str:
    """归一化:全角→半角、去空格,用于子串匹配。"""
    # 全角数字/字母→半角
    text = text.replace("\u3000", " ")
    # 全角数字转半角
    for i in range(10):
        text = text.replace(chr(0xFF10 + i), str(i))
    # 全角字母简单处理
    text = text.strip()
    return text


def check_1_schema():
    """校验一: 夹具文件 YAML 解析 + 字段完整性。"""
    errors = []
    warnings = []

    # ---- worldbook.yaml ----
    wb_path = EVAL_DIR / "worldbook.yaml"
    if not wb_path.exists():
        errors.append(f"worldbook.yaml 不存在: {wb_path}")
    else:
        with open(wb_path, encoding="utf-8") as f:
            wb = yaml.safe_load(f)
        if not isinstance(wb, dict):
            errors.append("worldbook.yaml 不是合法 dict")
        else:
            for key in ["facts", "forbidden"]:
                if key not in wb:
                    errors.append(f"worldbook.yaml 缺字段: {key}")
            for key in ["narrative_anchors", "factions", "timeline"]:
                if key not in wb:
                    warnings.append(f"worldbook.yaml 缺可选字段: {key}")

    # ---- characters.yaml ----
    ch_path = EVAL_DIR / "characters.yaml"
    if not ch_path.exists():
        errors.append(f"characters.yaml 不存在: {ch_path}")
    else:
        with open(ch_path, encoding="utf-8") as f:
            chars = yaml.safe_load(f)
        if not isinstance(chars, dict):
            errors.append("characters.yaml 不是合法 dict")
        else:
            # 按 B1 schema 检查每张卡
            required_fields = ["tier", "background", "personality"]
            for name, card in chars.items():
                if not isinstance(card, dict):
                    errors.append(f"characters.yaml: {name} 不是 dict")
                    continue
                for field in required_fields:
                    if field not in card:
                        errors.append(f"characters.yaml: {name} 缺必填字段 {field}")

    # ---- truth_files/ (序章, 4 files) ----
    tf_dir = EVAL_DIR / "truth_files"
    expected_tf = ["current_state.yaml", "particle_ledger.yaml",
                   "pending_hooks.yaml", "character_appearances.yaml"]
    for fname in expected_tf:
        fpath = tf_dir / fname
        if not fpath.exists():
            errors.append(f"truth_files/{fname} 不存在")
        else:
            with open(fpath, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data is None:
                errors.append(f"truth_files/{fname} 为空或解析失败")

    # ---- truth_files_frozen/ (FT1 + FT2) ----
    tff_dir = EVAL_DIR / "truth_files_frozen"
    expected_tff = [
        "FT1_current_state.yaml", "FT1_particle_ledger.yaml", "FT1_pending_hooks.yaml",
        "FT2_current_state.yaml", "FT2_particle_ledger.yaml", "FT2_pending_hooks.yaml",
    ]
    for fname in expected_tff:
        fpath = tff_dir / fname
        if not fpath.exists():
            errors.append(f"truth_files_frozen/{fname} 不存在")
        else:
            with open(fpath, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data is None:
                errors.append(f"truth_files_frozen/{fname} 为空或解析失败")

    # ---- sub_md/ (T1-T3) ----
    for t in ["T1", "T2", "T3"]:
        fpath = EVAL_DIR / "sub_md" / f"{t}.md"
        if not fpath.exists():
            errors.append(f"sub_md/{t}.md 不存在")
        else:
            content = fpath.read_text(encoding="utf-8")
            if not content.strip():
                errors.append(f"sub_md/{t}.md 为空")

    # ---- anchors.yaml ----
    anchors_path = EVAL_DIR / "anchors.yaml"
    if not anchors_path.exists():
        errors.append("anchors.yaml 不存在")
    else:
        with open(anchors_path, encoding="utf-8") as f:
            anchors = yaml.safe_load(f)
        if not isinstance(anchors, dict):
            errors.append("anchors.yaml 不是合法 dict")

    return errors, warnings


def check_2_anchor_consistency():
    """校验二: anchors.yaml 每条 canonical(及 aliases)是否出现在对应 sub-md 中。"""
    errors = []

    anchors_path = EVAL_DIR / "anchors.yaml"
    with open(anchors_path, encoding="utf-8") as f:
        anchors = yaml.safe_load(f)

    for chapter_key, chapter_data in anchors.items():
        sub_md_path = EVAL_DIR / "sub_md" / f"{chapter_key}.md"
        if not sub_md_path.exists():
            errors.append(f"[{chapter_key}] sub_md 不存在: {sub_md_path}")
            continue

        sub_md_text = normalize(sub_md_path.read_text(encoding="utf-8"))
        atomic_list = chapter_data.get("atomic", [])

        for anchor in atomic_list:
            aid = anchor["id"]
            canonical = normalize(anchor["canonical"])
            aliases = [normalize(a) for a in anchor.get("aliases", [])]

            found = False
            # 检查 canonical
            if canonical in sub_md_text:
                found = True
            # 检查 aliases
            if not found:
                for alias in aliases:
                    if alias and alias in sub_md_text:
                        found = True
                        break

            if not found:
                errors.append(
                    f"[{chapter_key}] {aid}: canonical='{anchor['canonical']}' "
                    f"及所有 aliases 在 sub_md 中未找到"
                )

    return errors


def check_3_composite_refs():
    """校验三: composite 的 members 引用的 id 全部存在。"""
    errors = []

    anchors_path = EVAL_DIR / "anchors.yaml"
    with open(anchors_path, encoding="utf-8") as f:
        anchors = yaml.safe_load(f)

    for chapter_key, chapter_data in anchors.items():
        atomic_list = chapter_data.get("atomic", [])
        composite_list = chapter_data.get("composite", [])

        # 收集本章所有 atomic id
        atomic_ids = {a["id"] for a in atomic_list}

        for comp in composite_list:
            comp_id = comp["id"]
            members = comp.get("members", [])
            for member_id in members:
                if member_id not in atomic_ids:
                    errors.append(
                        f"[{chapter_key}] composite {comp_id} 引用了不存在的 member: {member_id}"
                    )

    return errors


def main():
    print("=" * 60)
    print("eval_set_v0 三重校验")
    print("=" * 60)

    all_errors = []
    all_warnings = []

    # 校验一
    print("\n--- 校验一: 夹具 Schema ---")
    e1, w1 = check_1_schema()
    all_errors.extend(e1)
    all_warnings.extend(w1)
    if e1:
        print(f"  错误 ({len(e1)}):")
        for e in e1:
            print(f"    [ERROR] {e}")
    if w1:
        print(f"  警告 ({len(w1)}):")
        for w in w1:
            print(f"    [WARN] {w}")
    if not e1 and not w1:
        print("  通过")

    # 校验二
    print("\n--- 校验二: 锚点与 sub-md 一致性 ---")
    e2 = check_2_anchor_consistency()
    all_errors.extend(e2)
    if e2:
        print(f"  不一致 ({len(e2)}):")
        for e in e2:
            print(f"    [MISMATCH] {e}")
    else:
        print("  通过: 所有 canonical/aliases 均在 sub-md 中找到")

    # 校验三
    print("\n--- 校验三: composite 引用完整性 ---")
    e3 = check_3_composite_refs()
    all_errors.extend(e3)
    if e3:
        print(f"  悬空引用 ({len(e3)}):")
        for e in e3:
            print(f"    [DANGLING] {e}")
    else:
        print("  通过: 所有 composite members 引用有效")

    # 汇总
    print("\n" + "=" * 60)
    if all_errors:
        print(f"校验未通过: {len(all_errors)} 个错误")
        sys.exit(1)
    else:
        print("三重校验全部通过")
        sys.exit(0)


if __name__ == "__main__":
    main()
