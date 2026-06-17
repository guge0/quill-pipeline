"""P6-2 题材模板 monkey-patch installer。

学 P6-人味 install_anti_mechanical_patch 模式,但目标不同:
- P6-人味:patch chapter_writer.build_layer3_constraints(pipeline 函数内 lazy import)
- P6-2:patch v3_opening.build_planning_prompt(pipeline module-level from-import)
  → 必须同时 patch pipeline.build_planning_prompt 本地绑定

注入位置:build_planning_prompt 返回值的 "## 输出格式" 标记之前。
注入内容:由 scripts.p6_2_render_block.render_genre_block 生成的 genre_block。

§6 禁区零触碰:v3_opening.py 文件本身不动,运行时 monkey-patch。
"""
from pathlib import Path

from p6_2_render_block import render_genre_block


def _patched_factory(original, yaml_path):
    """构造 patched 函数。抽出来便于单测注入 fake original。"""

    def patched(
        outline,
        characters=None,
        truth_files_block="",
        worldbook_prompt="",
        chapter_num=0,
        anchor_block="",
        **kwargs,
    ):
        base = original(
            outline=outline,
            characters=characters,
            truth_files_block=truth_files_block,
            worldbook_prompt=worldbook_prompt,
            chapter_num=chapter_num,
            anchor_block=anchor_block,
            **kwargs,
        )
        genre_block = render_genre_block(yaml_path, chapter_num)
        marker = "## 输出格式"
        if marker in base:
            return base.replace(marker, f"{genre_block}\n\n{marker}", 1)
        return base + "\n\n" + genre_block

    return patched


def install_genre_patch(yaml_path) -> None:
    """安装 monkey-patch。双绑定:vo + pipe。

    使用:在 pipeline 调用前调用一次。多次调用安全(基于当前 original)。
    """
    import biyu.prompts.v3_opening as vo
    import biyu.pipeline as pipe

    yaml_path = Path(yaml_path)

    # 用当前 vo.build_planning_prompt 作为 original(允许测试时已 fake)
    original = vo.build_planning_prompt
    patched = _patched_factory(original, yaml_path)

    vo.build_planning_prompt = patched
    pipe.build_planning_prompt = patched  # 关键:pipeline module-level from-import 本地绑定

    # D-45 启动断言(双绑定)
    assert vo.build_planning_prompt is patched, "vo patch 未生效"
    assert pipe.build_planning_prompt is patched, "pipe patch 未生效(关键)"
    assert vo.build_planning_prompt is pipe.build_planning_prompt, "双绑定不一致"


if __name__ == "__main__":
    # 独立运行:仅 print patched prompt,便于人工核验
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    ap = argparse.ArgumentParser()
    ap.add_argument("yaml", type=Path)
    ap.add_argument("--chapter", type=int, default=1)
    args = ap.parse_args()
    install_genre_patch(args.yaml)
    import biyu.prompts.v3_opening as vo
    print(vo.build_planning_prompt(outline="测试", chapter_num=args.chapter))
