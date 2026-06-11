#!/usr/bin/env python3
"""D-47: 捕获 Writer 首个请求体并落盘。

只跑 T1 的 Architect + Writer（不跑后续阶段），拦截 httpx 请求体。
"""
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "eval_set_v0"
BASELINE_DIR = EVAL_DIR / "baseline"
BOOK_DIR = PROJECT_ROOT / "data" / "EV1_D47_capture"


async def main():
    import shutil
    import yaml

    BOOK_DIR.mkdir(parents=True, exist_ok=True)

    # Setup minimal book dir
    meta = {
        "title": "EV1 D47 capture",
        "genre": "都市悬疑",
        "chapter_target_words": 5000,
        "chapter_min_words": 3000,
        "context_mode": "long_context",
    }
    (BOOK_DIR / "book.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(EVAL_DIR / "worldbook.yaml", BOOK_DIR / "worldbook.yaml")

    with open(EVAL_DIR / "characters.yaml", encoding="utf-8") as f:
        chars_dict = yaml.safe_load(f)
    chars_list = [{"name": n, **f} for n, f in chars_dict.items() if isinstance(f, dict)]
    (BOOK_DIR / "characters.yaml").write_text(
        yaml.dump({"characters": chars_list}, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )

    tf_dst = BOOK_DIR / "truth_files"
    tf_dst.mkdir(parents=True, exist_ok=True)
    for yaml_file in (EVAL_DIR / "truth_files").glob("*.yaml"):
        content = yaml_file.read_text(encoding="utf-8")
        (tf_dst / (yaml_file.stem + ".md")).write_text(content, encoding="utf-8")

    outline_dir = BOOK_DIR / "outlines"
    outline_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(EVAL_DIR / "sub_md" / "T1.md", outline_dir / "ch1.md")

    # 拦截 httpx.AsyncClient.post
    captured = []
    original_post = httpx.AsyncClient.post

    async def capturing_post(self, url, **kwargs):
        if not captured and "deepseek" in str(url) and "chat/completions" in str(url):
            body = {
                "url": str(url),
                "json_keys": list(kwargs.get("json", {}).keys()) if kwargs.get("json") else [],
                "messages_count": len(kwargs.get("json", {}).get("messages", [])),
                "model": kwargs.get("json", {}).get("model", ""),
                "temperature": kwargs.get("json", {}).get("temperature"),
                "max_tokens": kwargs.get("json", {}).get("max_tokens"),
                "messages_preview": [],
            }
            for m in kwargs.get("json", {}).get("messages", []):
                body["messages_preview"].append({
                    "role": m.get("role"),
                    "content_length": len(m.get("content", "")) if m.get("content") else 0,
                    "content_first_200": (m.get("content", "") or "")[:200],
                })
            captured.append(body)
        return await original_post(self, url, **kwargs)

    httpx.AsyncClient.post = capturing_post

    # 只跑 Architect + Writer（不跑完整管线）
    from biyu.config import BookConfig, get_registry
    from biyu.worldbook import load_worldbook, build_worldbook_prompt
    from biyu.config import load_characters_yaml
    from biyu.truth_files import read_all_truth_files
    from biyu.prompts.chapter_writer import build_writer_prompt_v4, build_layer2_context
    from biyu.wordguard import count_cjk_chars
    from biyu.prompts.v3_opening import build_planning_prompt

    book = BookConfig(BOOK_DIR)
    registry = get_registry()
    wb = load_worldbook(BOOK_DIR)
    wb_prompt = build_worldbook_prompt(wb)
    characters = load_characters_yaml(BOOK_DIR)

    outline = (BOOK_DIR / "outlines" / "ch1.md").read_text(encoding="utf-8")

    truth_data = read_all_truth_files(BOOK_DIR)
    truth_block = ""
    for name, content in truth_data.items():
        if content.strip():
            truth_block += f"=== {name} ===\n{content}\n\n"

    # Architect
    planner_adapter = registry.get_adapter_for_stage("planner")
    planning_content = build_planning_prompt(
        outline=outline, characters=characters, truth_files_block=truth_block,
        worldbook_prompt=wb_prompt, chapter_num=1,
    )
    planning_resp = await planner_adapter.generate([{"role": "user", "content": planning_content}])
    planning_text = planning_resp.text

    # Writer (v4 prompt)
    writer_adapter = registry.get_adapter_for_stage("writer")
    system_prompt, user_prompt = build_writer_prompt_v4(
        chapter_num=1, worldbook=wb, worldbook_prompt=wb_prompt,
        characters=characters, truth_files_block=truth_block,
        prev_tail="", context_block="", outline=planning_text,
        planning="", target_words=5000, present_characters=["江叙白", "聂守仁", "何沛", "报刊亭老板"],
    )
    stable_layer2 = build_layer2_context(
        worldbook_prompt=wb_prompt, characters=characters,
        truth_files_block="", prev_tail="", context_block="", outline="", planning="",
    )
    cacheable_prefix = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": stable_layer2},
        {"role": "assistant", "content": "已加载世界观和角色卡。"},
    ]
    dynamic_content = f"{user_prompt}\n\n现在开始写第 1 章正文。只输出正文,不要输出元信息。"
    dynamic_messages = [{"role": "user", "content": dynamic_content}]

    writer_resp = await writer_adapter.generate(
        dynamic_messages, cacheable_prefix=cacheable_prefix,
        temperature=0.8, max_tokens=16384,
    )

    # 恢复
    httpx.AsyncClient.post = original_post

    # 落盘 D-47
    if captured:
        # 第二个捕获的是 Writer（第一个是 Architect）
        writer_body = None
        for c in captured:
            if c.get("messages_count", 0) >= 3:  # Writer 有 prefix + dynamic
                writer_body = c
                break
        if not writer_body and len(captured) > 1:
            writer_body = captured[1]  # 第二个请求通常是 Writer
        if not writer_body:
            writer_body = captured[-1]  # fallback

        req_path = BASELINE_DIR / "writer_request_body.json"
        req_path.write_text(json.dumps(writer_body, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"D-47 request body saved: {req_path}")
        print(f"  Captured {len(captured)} requests, writer body has {writer_body.get('messages_count')} messages")
    else:
        print("No requests captured!")

    # 确认冻结 truth 注入
    if captured:
        for c in captured:
            for mp in c.get("messages_preview", []):
                if "clue-001" in mp.get("content_first_200", "") or "particle_ledger" in mp.get("content_first_200", ""):
                    print("truth injection confirmed: found truth file content in writer messages")
                    break


if __name__ == "__main__":
    asyncio.run(main())
