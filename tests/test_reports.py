from __future__ import annotations

import unittest

from stock_assist.reports import markdown_report_to_html


class ReportRenderingTests(unittest.TestCase):
    def test_generic_markdown_renderer_still_uses_collapsed_sections(self) -> None:
        html = markdown_report_to_html("# T\n\n## S\n\n- evidence")
        self.assertIn('<details class="report-section">', html)
        self.assertNotIn('id="route-today"', html)

    def test_markdown_links_render_as_labelled_anchors(self) -> None:
        html = markdown_report_to_html("# T\n\n## S\n\n- [主题](https://example.com/read.php?tid=1)")
        self.assertIn('href="https://example.com/read.php?tid=1"', html)
        self.assertIn('>主题</a>', html)
        self.assertNotIn('[主题](', html)

    def test_nga_report_renders_visual_summary_before_collapsed_evidence(self) -> None:
        markdown = """# NGA 大时代今日话题 2026-07-15

## 情绪仪表盘

| 指标 | 当前读数 | 研究判断 |
|---|---:|---|
| 整体方向 | 明显看空 | 看空占主导 |
| 看多 / 中性 / 看空 | 20% / 17% / 63% | 排除大V |
| 风险偏好 | 25 / 100 | 偏低 |
| 恐慌强度 | 78 / 100 | 偏高 |
| 亢奋强度 | 32 / 100 | 局部升温 |
| 多空分歧 | 74 / 100 | 分歧高 |
| 情绪阶段 | 冰点候选 | 待历史验证 |

### 板块温度

- 科技：方向明显看空；恐慌偏高。
- 创新药：方向偏多；拥挤度上升。

## 大V观点与转向

- **fuelish（uid=1）｜中期科技偏多、短线谨慎**：长期帖补回 8 条本人回复。

## 1. 科技仍在出清，反弹可信度不足

论坛情绪从期待修复转向谨慎，真正需要观察的是反弹能否延续。
"""
        html = markdown_report_to_html(markdown)
        self.assertIn('class="sentiment-stack"', html)
        self.assertIn('aria-label="看多 20%，中性 17%，看空 63%"', html)
        self.assertIn('class="kol-list"', html)
        self.assertIn("先读判断，再展开证据", html)
        self.assertIn('<details class="report-section">', html)


if __name__ == "__main__":
    unittest.main()
