"""P6-1A Step 4: Run Writer + multi_agent Editor for CH28.

Uses the approved Architect outline from Step 3.
Captures Writer's first LLM request body for D-47 evidence.

Outputs:
  outputs/P6-1A/ch28_new.md
  outputs/P6-1A/llm_request_body_writer_first_call.json
  outputs/P6-1A/editor_issues_ch28_new.json
  outputs/P6-1A/run_log_ch28_new.json
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

BOOK_DIR = REPO_ROOT / "data" / "EXAMPLE_PROTAGONIST_T-P3-A验证"
OUTPUT_DIR = REPO_ROOT / "outputs" / "P6-1A"

_original_post = httpx.AsyncClient.post


async def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    run_log = {"stages": [], "boundary_events": [], "total_cost": 0.0}
    captured_bodies = []

    async def capturing_post(self, url, **kwargs):
        body = kwargs.get("json")
        if body is not None:
            captured_bodies.append({"url": str(url), "payload": body})
        return await _original_post(self, url, **kwargs)

    # ---- Load data ----
    from biyu.config import BookConfig, load_characters_yaml
    from biyu.worldbook import load_worldbook, build_worldbook_prompt
    from biyu.truth_files import read_all_truth_files
    from biyu.config import get_registry
    from biyu.prompts.chapter_writer import (
        build_writer_prompt_v4, build_layer2_context,
        build_layer1_hard_rules, build_layer3_constraints,
    )
    from biyu.pipeline import (
        _load_prev_chapter_tail, _build_context_block,
        _parse_present_characters, _call_with_retry,
        _fix_chapter_number,
    )
    from biyu.wordguard import enforce_floor, count_cjk_chars

    book = BookConfig(BOOK_DIR)
    meta = book.load_meta()
    chapter_num = 28
    target_words = meta.get("chapter_target_words", 5000)
    min_words = meta.get("chapter_min_words", 4250)
    context_mode = meta.get("context_mode", "long_context")

    # Load approved planning_text (Architect outline)
    planning_path = OUTPUT_DIR / "ch28_creative_outline.md"
    planning_text = planning_path.read_text(encoding="utf-8")
    print(f"Approved outline: {len(planning_text)} chars")

    # Load sub-md (for present_characters parsing only)
    outline_path = REPO_ROOT / "data" / "sub_md" / "ch28.md"
    outline = outline_path.read_text(encoding="utf-8")

    # Worldbook
    wb = load_worldbook(BOOK_DIR)
    worldbook_prompt = build_worldbook_prompt(wb)
    print(f"worldbook: {len(worldbook_prompt)} chars")

    # Characters
    characters = load_characters_yaml(BOOK_DIR)
    print(f"characters: {len(characters)} loaded")

    # Present characters (from sub-md frontmatter)
    present_characters = _parse_present_characters(outline, BOOK_DIR)
    print(f"present_characters: {present_characters}")

    # Truth files
    truth_files_block = ""
    truth_data = read_all_truth_files(BOOK_DIR)
    for name, content in truth_data.items():
        if content.strip():
            truth_files_block += f"=== {name} ===\n{content}\n\n"
    print(f"truth_files: {len(truth_files_block)} chars")

    # Prev tail
    prev_tail = _load_prev_chapter_tail(BOOK_DIR, chapter_num)
    print(f"prev_tail: {len(prev_tail)} chars")

    # Context block
    context_block, _ = _build_context_block(BOOK_DIR, chapter_num, context_mode)
    print(f"context_block: {len(context_block)} chars")

    # ---- Registry & Adapters ----
    registry = get_registry()
    writer_adapter = registry.get_adapter_for_stage("writer")
    planner_adapter = registry.get_adapter_for_stage("planner")
    print(f"Writer adapter: {writer_adapter.model_name}")
    print()

    total_cost = 0.0

    # ================================================================
    # Stage: Writer
    # ================================================================
    print("=" * 50)
    print("[Writer] Building prompt...")
    t0 = time.time()

    system_prompt, user_prompt = build_writer_prompt_v4(
        chapter_num=chapter_num,
        worldbook=wb,
        worldbook_prompt=worldbook_prompt,
        characters=characters,
        truth_files_block=truth_files_block,
        prev_tail=prev_tail,
        context_block=context_block,
        outline=planning_text,     # P6-1A: approved outline
        planning="",                # P6-1A: no separate planning
        target_words=target_words,
        present_characters=present_characters,
    )

    # Cacheable prefix (stable across chapters)
    stable_layer2 = build_layer2_context(
        worldbook_prompt=worldbook_prompt,
        characters=characters,
        truth_files_block="",
        prev_tail="",
        context_block="",
        outline="",
        planning="",
    )
    cacheable_prefix = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": stable_layer2},
        {"role": "assistant", "content": "已加载世界观和角色卡。"},
    ]

    # Dynamic content
    layer1 = build_layer1_hard_rules(chapter_num, wb)
    variable_layer2 = build_layer2_context(
        worldbook_prompt="",
        characters=[],
        truth_files_block=truth_files_block,
        prev_tail=prev_tail,
        context_block=context_block,
        outline=planning_text,
        planning="",
    )
    layer3 = build_layer3_constraints(target_words)
    dynamic_content = (
        f"{layer1}\n\n"
        f"{variable_layer2}\n\n"
        f"{layer3}\n\n"
        f"现在开始写第 {chapter_num} 章正文。只输出正文,不要输出元信息。"
    )
    dynamic_messages = [{"role": "user", "content": dynamic_content}]

    print(f"[Writer] Calling LLM (dynamic={len(dynamic_content)} chars)...")
    writer_t0 = time.time()

    with patch.object(httpx.AsyncClient, "post", capturing_post):
        writer_resp = await _call_with_retry(
            writer_adapter, dynamic_messages,
            cacheable_prefix=cacheable_prefix,
            temperature=0.8,
            max_tokens=16384,
        )

    writer_elapsed = time.time() - writer_t0
    total_cost += writer_resp.cost
    skeleton_text = writer_resp.text
    skeleton_count = count_cjk_chars(skeleton_text)
    print(f"[Writer] Done: {writer_elapsed:.1f}s, CNY{writer_resp.cost:.4f}, {skeleton_count} chars")
    run_log["stages"].append({
        "stage": "writer",
        "elapsed_s": round(writer_elapsed, 1),
        "cost_cny": round(writer_resp.cost, 4),
        "char_count": skeleton_count,
    })

    # Budget check after Writer
    architect_total = 0.32  # from Step 3 runs
    running_total = architect_total + total_cost
    print(f"[Budget] Running total: CNY{running_total:.4f} (alarm=0.65, hard_stop=0.90)")
    if running_total > 0.65:
        print(f"[Budget] WARNING: Approaching alarm threshold!")
    if running_total > 0.90:
        print(f"[Budget] HARD STOP EXCEEDED! Stopping.")
        run_log["boundary_events"].append("BUDGET_HARD_STOP after Writer")
        _save_outputs(skeleton_text, captured_bodies, None, run_log, total_cost)
        return False

    # ---- V3 self-continuation if short ----
    if skeleton_count < 4500:
        remaining = target_words - skeleton_count
        print(f"[Writer+] Self-continuation ({skeleton_count} < 4500, target +{remaining})...")
        cont_prompt = (
            f"你刚才写的章节到这里：\n{skeleton_text[-2000:]}\n\n"
            f"大纲还有未完成部分：\n{outline}\n\n"
            f"请继续写,风格和前文保持一致,不要重复已写内容。目标再写 {remaining} 字。"
        )
        cont_messages = [
            {"role": "system", "content": "你是中文网文作者。"},
            {"role": "user", "content": cont_prompt},
        ]
        t_cont = time.time()
        with patch.object(httpx.AsyncClient, "post", capturing_post):
            cont_resp = await _call_with_retry(writer_adapter, cont_messages, temperature=0.8, max_tokens=16384)
        cont_elapsed = time.time() - t_cont
        total_cost += cont_resp.cost
        if cont_resp.text and cont_resp.text.strip():
            skeleton_text = skeleton_text + "\n" + cont_resp.text
            skeleton_count = count_cjk_chars(skeleton_text)
            print(f"[Writer+] Done: {cont_elapsed:.1f}s, CNY{cont_resp.cost:.4f}, now {skeleton_count} chars")
            run_log["stages"].append({
                "stage": "writer_continuation",
                "elapsed_s": round(cont_elapsed, 1),
                "cost_cny": round(cont_resp.cost, 4),
                "char_count": skeleton_count,
            })
        else:
            print("[Writer+] Empty response, skipped")
            run_log["boundary_events"].append("writer_continuation_empty_response")

    # ---- Chapter number fix ----
    skeleton_text = _fix_chapter_number(skeleton_text, chapter_num)
    print()

    # ================================================================
    # Stage: WordGuard
    # ================================================================
    print("=" * 50)
    print(f"[WordGuard] Checking ({skeleton_count}/{min_words})...")
    text_after_guard = skeleton_text

    async def _continuation_fn(current_text, remaining):
        cont_prompt = (
            f"以下是上一章正文(已写{count_cjk_chars(current_text)}字,目标{target_words}字):\n\n"
            f"{current_text[-1500:]}\n\n"
            f"请从断点处自然续写约{remaining}字,保持风格和人物一致。\n"
            f"只输出续写正文,不要输出说明。"
        )
        messages = [{"role": "user", "content": cont_prompt}]
        with patch.object(httpx.AsyncClient, "post", capturing_post):
            resp = await _call_with_retry(planner_adapter, messages)
        return resp.text

    wg_t0 = time.time()
    guard_result = await enforce_floor(
        text=skeleton_text,
        target=target_words,
        floor=min_words,
        continuation_fn=_continuation_fn,
    )
    wg_elapsed = time.time() - wg_t0
    text_after_guard = guard_result.text
    print(f"[WordGuard] {'Continued' if guard_result.continued else 'Passed'}: "
          f"{skeleton_count} -> {guard_result.word_count} chars, {wg_elapsed:.1f}s")
    run_log["stages"].append({
        "stage": "wordguard",
        "elapsed_s": round(wg_elapsed, 1),
        "continued": guard_result.continued,
        "before_chars": skeleton_count,
        "after_chars": guard_result.word_count,
    })
    if guard_result.warning:
        run_log["boundary_events"].append(f"wordguard_warning: {guard_result.warning}")
    print()

    # ================================================================
    # Stage: Post-processing
    # ================================================================
    # Dash fixer
    try:
        from biyu.postproc.dash_fixer import fix_dashes
        dash_result = fix_dashes(text_after_guard)
        if dash_result.original_count != dash_result.fixed_count:
            text_after_guard = dash_result.fixed_text
            print(f"[dash_fixer] {dash_result.original_count} -> {dash_result.fixed_count}")
        else:
            print(f"[dash_fixer] No changes needed")
    except Exception as e:
        print(f"[dash_fixer] Skipped: {e}")
        run_log["boundary_events"].append(f"dash_fixer_error: {e}")

    # Wenyan fixer
    try:
        from biyu.postproc.wenyan_fixer import fix_wenyan
        from biyu.pipeline import _detect_secret_realm
        in_sr = _detect_secret_realm(outline)
        wenyan_result = fix_wenyan(text_after_guard, in_secret_realm=in_sr)
        if wenyan_result.replacements:
            text_after_guard = wenyan_result.fixed_text
            total_replaced = sum(r["count"] for r in wenyan_result.replacements)
            print(f"[wenyan_fixer] Fixed {total_replaced}")
        else:
            print(f"[wenyan_fixer] No changes")
    except Exception as e:
        print(f"[wenyan_fixer] Skipped: {e}")
        run_log["boundary_events"].append(f"wenyan_fixer_error: {e}")

    # Grammar check
    try:
        from biyu.grammar_check.checker import check_chapter as grammar_check, auto_fix as grammar_auto_fix
        grammar_result = grammar_check(text_after_guard, BOOK_DIR)
        if grammar_result.has_issues:
            text_after_guard, grammar_fixed = grammar_auto_fix(text_after_guard, grammar_result)
            print(f"[grammar_check] Fixed {grammar_fixed}")
        else:
            print(f"[grammar_check] Passed")
    except Exception as e:
        print(f"[grammar_check] Skipped: {e}")
        run_log["boundary_events"].append(f"grammar_check_error: {e}")

    print()

    # ================================================================
    # Stage: multi_agent Editor
    # ================================================================
    print("=" * 50)
    print("[Editor] multi_agent (A/B/C)...")

    # NOTE: load_editor_config() resolves to src/config/editor.yaml which doesn't
    # exist, so it always falls back to {"mode": "single"}. We bypass the config
    # and call review_chapter_multi_agent directly — this is the intended P6-1A mode.
    from biyu.editor.multi_agent import review_chapter_multi_agent
    from biyu.editor.merge import render_audit_report

    prev_tail_for_editor = ""
    prev_ch = BOOK_DIR / "chapters" / f"ch{chapter_num - 1}.md"
    if prev_ch.exists():
        prev_tail_for_editor = prev_ch.read_text(encoding="utf-8")[-500:]

    editor_adapter = registry.get_adapter_for_stage("writer")

    ed_t0 = time.time()
    try:
        with patch.object(httpx.AsyncClient, "post", capturing_post):
            merge_result = await review_chapter_multi_agent(
                chapter_num=chapter_num,
                chapter_text=text_after_guard,
                book_dir=BOOK_DIR,
                adapter=editor_adapter,
                prev_chapter_tail=prev_tail_for_editor,
            )
        ed_elapsed = time.time() - ed_t0
        total_cost += merge_result.total_cost
        print(f"[Editor] Done: {ed_elapsed:.1f}s, CNY{merge_result.total_cost:.4f}")
        print(f"[Editor] Issues: {merge_result.total_issues} total, "
              f"{len(merge_result.high_issues)} high severity")
        if merge_result.fallback_used:
            print(f"[Editor] Fallback used (budget exceeded)")
            run_log["boundary_events"].append("editor_fallback_used")

        run_log["stages"].append({
            "stage": "editor_multi_agent",
            "elapsed_s": round(ed_elapsed, 1),
            "cost_cny": round(merge_result.total_cost, 4),
            "total_issues": merge_result.total_issues,
            "high_severity_issues": len(merge_result.high_issues),
            "fallback_used": merge_result.fallback_used,
        })

        # Build editor issues JSON
        editor_issues = {
            "chapter": "ch28",
            "mode": "multi_agent",
            "total_issues": merge_result.total_issues,
            "high_severity_count": len(merge_result.high_issues),
            "fallback_used": merge_result.fallback_used,
            "issues": [],
        }
        for issue in merge_result.all_issues:
            editor_issues["issues"].append({
                "agent": getattr(issue, "agent", "unknown"),
                "type": issue.type,
                "severity": issue.severity,
                "description": issue.description,
                "suggestion": issue.suggestion,
            })
        if merge_result.high_issues:
            print("[Editor] High severity types:",
                  ", ".join(i.type for i in merge_result.high_issues))

    except Exception as e:
        ed_elapsed = time.time() - ed_t0
        print(f"[Editor] ERROR: {e}")
        run_log["boundary_events"].append(f"editor_error: {str(e)}")
        editor_issues = {"chapter": "ch28", "mode": "multi_agent", "error": str(e)}
        merge_result = None

    print()

    # ================================================================
    # Final budget check
    # ================================================================
    running_total = 0.32 + total_cost
    print(f"[Budget] Final total: CNY{running_total:.4f} (architect=0.32 + writer+editor={total_cost:.4f})")
    run_log["total_cost"] = round(running_total, 4)
    if running_total > 0.90:
        run_log["boundary_events"].append("BUDGET_HARD_STOP")

    # ================================================================
    # Save outputs
    # ================================================================
    _save_outputs(text_after_guard, captured_bodies,
                  editor_issues if 'editor_issues' in dir() else None,
                  run_log, total_cost)

    # Print chapter text for review
    print("=" * 50)
    print(f"CH28 NEW TEXT ({len(text_after_guard)} chars, {count_cjk_chars(text_after_guard)} cjk chars):")
    print("=" * 50)
    print(text_after_guard[:3000])
    if len(text_after_guard) > 3000:
        print(f"\n... [truncated, total {len(text_after_guard)} chars] ...")
        print(f"\n--- LAST 1000 chars ---")
        print(text_after_guard[-1000:])

    return True


def _save_outputs(text, captured_bodies, editor_issues, run_log, writer_editor_cost):
    # CH28 text
    ch_path = OUTPUT_DIR / "ch28_new.md"
    ch_path.write_text(text, encoding="utf-8")
    print(f"Saved: {ch_path}")

    # D-47 Writer request body
    if captured_bodies:
        body = captured_bodies[0]["payload"]
        # Check for outline/planning in messages
        has_creative_outline = False
        for m in body.get("messages", []):
            content = str(m.get("content", ""))
            if "创作者细纲" in content or "戏核" in content:
                has_creative_outline = True
                break

        evidence = {
            "capture_note": "D-47 取证: P6-1A Writer 首次调用发给 LLM 的实际请求体",
            "chapter": "ch28",
            "stage": "writer",
            "capture_method": "httpx post monkey-patch",
            "total_api_calls": len(captured_bodies),
            "model": body.get("model"),
            "creative_outline_in_messages": has_creative_outline,
            "messages_summary": [
                {"role": m.get("role"), "content_length": len(str(m.get("content", "")))}
                for m in body.get("messages", [])
            ],
            "messages": body.get("messages"),
        }
        ev_path = OUTPUT_DIR / "llm_request_body_writer_first_call.json"
        with open(ev_path, "w", encoding="utf-8") as f:
            json.dump(evidence, f, ensure_ascii=False, indent=2)
        print(f"Saved: {ev_path}")
        print(f"  creative_outline in messages: {has_creative_outline}")

    # Editor issues
    if editor_issues:
        ed_path = OUTPUT_DIR / "editor_issues_ch28_new.json"
        with open(ed_path, "w", encoding="utf-8") as f:
            json.dump(editor_issues, f, ensure_ascii=False, indent=2)
        print(f"Saved: {ed_path}")

    # Run log
    run_log["writer_editor_cost_cny"] = round(writer_editor_cost, 4)
    log_path = OUTPUT_DIR / "run_log_ch28_new.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(run_log, f, ensure_ascii=False, indent=2)
    print(f"Saved: {log_path}")


if __name__ == "__main__":
    import os
    os.environ["PYTHONIOENCODING"] = "utf-8"
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
