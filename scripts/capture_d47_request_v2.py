#!/usr/bin/env python3
"""D-47: 捕获 Writer 首个请求体并落盘 (v2)。

直接拦截所有 httpx.AsyncClient.post 调用，取第二个请求(Writer)。
"""
import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "eval_set_v0"
BASELINE_DIR = EVAL_DIR / "baseline"
BOOK_DIR = PROJECT_ROOT / "data" / "EV1_D47_capture"


async def main():
    import shutil
    import yaml
    import httpx

    BOOK_DIR.mkdir(parents=True, exist_ok=True)

    # Setup
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

    # 拦截所有 httpx POST 请求
    all_captured = []
    original_post = httpx.AsyncClient.post

    async def capturing_post(self, url, **kwargs):
        if "deepseek" in str(url) and "chat/completions" in str(url):
            body = kwargs.get("json", {})
            entry = {
                "url": str(url),
                "model": body.get("model", ""),
                "messages_count": len(body.get("messages", [])),
                "temperature": body.get("temperature"),
                "max_tokens": body.get("max_tokens"),
                "stream": body.get("stream"),
                "has_tools": bool(body.get("tools")),
            }
            # 消息摘要
            msgs_summary = []
            for m in body.get("messages", []):
                content = m.get("content", "")
                msgs_summary.append({
                    "role": m.get("role"),
                    "content_length": len(content),
                    "content_first_300": content[:300],
                })
            entry["messages"] = msgs_summary
            all_captured.append(entry)
        return await original_post(self, url, **kwargs)

    httpx.AsyncClient.post = capturing_post

    # 跑管线
    from biyu.config import BookConfig, get_registry
    from biyu.worldbook import load_worldbook, build_worldbook_prompt
    from biyu.config import load_characters_yaml
    from biyu.truth_files import read_all_truth_files
    from biyu.prompts.chapter_writer import build_writer_prompt_v4, build_layer2_context
    from biyu.prompts.v3_opening import build_planning_prompt

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
    print(f"Architect done: {len(planning_text)} chars")

    # Writer
    writer_adapter = registry.get_adapter_for_stage("writer")
    system_prompt, user_prompt = build_writer_prompt_v4(
        chapter_num=1, worldbook=wb, worldbook_prompt=wb_prompt,
        characters=characters, truth_files_block=truth_block,
        prev_tail="", context_block="", outline=planning_text,
        planning="", target_words=5000,
        present_characters=["江叙白", "聂守仁", "何沛", "报刊亭老板"],
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
    print(f"Writer done: {len(writer_resp.text)} chars")

    # 恢复
    httpx.AsyncClient.post = original_post

    # 落盘
    print(f"\nCaptured {len(all_captured)} requests:")
    for i, c in enumerate(all_captured):
        print(f"  [{i}] model={c['model']}, msgs={c['messages_count']}, has_tools={c['has_tools']}")

    # Writer 请求 = 第二个（如果第一个是 Architect）
    writer_body = None
    if len(all_captured) >= 2:
        writer_body = all_captured[1]  # Second request is Writer
    elif len(all_captured) == 1:
        writer_body = all_captured[0]

    if writer_body:
        req_path = BASELINE_DIR / "writer_request_body.json"
        req_path.write_text(json.dumps(writer_body, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nD-47 saved: {req_path}")
        print(f"  messages_count: {writer_body['messages_count']}")

        # 确认 truth 注入
        truth_found = False
        for m in writer_body.get("messages", []):
            text = m.get("content_first_300", "")
            if "clue-001" in text or "particle_ledger" in text or "current_state" in text:
                truth_found = True
                break
        print(f"  truth injection confirmed: {truth_found}")
    else:
        print("ERROR: No writer request captured!")


if __name__ == "__main__":
    asyncio.run(main())
