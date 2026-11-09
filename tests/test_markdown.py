import json
import shutil
import subprocess
import unittest
from pathlib import Path

from answers import DEFAULT_INSTRUCTIONS


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def parse(text):
    script = (
        f"const {{parseMarkdown}} = require({json.dumps(str(ROOT / 'static/markdown.js'))});"
        f"console.log(JSON.stringify(parseMarkdown({json.dumps(text)})));"
    )
    result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=20, check=True)
    return json.loads(result.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class ParseMarkdownTest(unittest.TestCase):
    def test_headings_keep_their_level(self):
        blocks = parse("# ראשי\n\n## משני\n\n### שלישי")
        self.assertEqual([(b["type"], b["level"]) for b in blocks],
                         [("heading", 1), ("heading", 2), ("heading", 3)])
        self.assertEqual(blocks[1]["inline"], [{"type": "text", "text": "משני"}])

    def test_paragraph_joins_adjacent_lines(self):
        blocks = parse("שורה אחת\nשורה שתיים\n\nפסקה חדשה")
        self.assertEqual([b["type"] for b in blocks], ["paragraph", "paragraph"])
        self.assertEqual(blocks[0]["inline"], [{"type": "text", "text": "שורה אחת שורה שתיים"}])

    def test_nested_list_becomes_children(self):
        blocks = parse("- ראשון\n- שני\n  - פנימי\n  - עוד פנימי\n- שלישי")
        self.assertEqual(len(blocks), 1)
        items = blocks[0]["items"]
        self.assertFalse(blocks[0]["ordered"])
        self.assertEqual(len(items), 3)
        self.assertEqual([len(item["children"]) for item in items], [0, 1, 0])
        self.assertEqual(len(items[1]["children"][0]["items"]), 2)

    def test_ordered_list(self):
        blocks = parse("1. ראשון\n2. שני")
        self.assertTrue(blocks[0]["ordered"])
        self.assertEqual(len(blocks[0]["items"]), 2)

    def test_inline_code_and_emphasis(self):
        inline = parse("קוד `x` ו-**חזק** ו-*נטוי*")[0]["inline"]
        self.assertEqual(inline, [
            {"type": "text", "text": "קוד "}, {"type": "code", "text": "x"},
            {"type": "text", "text": " ו-"}, {"type": "strong", "text": "חזק"},
            {"type": "text", "text": " ו-"}, {"type": "em", "text": "נטוי"},
        ])

    def test_html_stays_plain_text(self):
        text = '<img src=x onerror="alert(1)"> **<script>**'
        inline = parse(text)[0]["inline"]
        self.assertEqual(inline[0], {"type": "text", "text": '<img src=x onerror="alert(1)"> '})
        self.assertEqual(inline[1], {"type": "strong", "text": "<script>"})

    def test_fenced_code_is_kept_verbatim(self):
        blocks = parse("```json\n# לא כותרת\n- לא רשימה\n```\nאחרי")
        self.assertEqual(blocks[0], {"type": "code", "text": "# לא כותרת\n- לא רשימה"})
        self.assertEqual(blocks[1]["type"], "paragraph")

    def test_unclosed_fence_does_not_lose_text(self):
        self.assertEqual(parse("```\nטקסט")[0], {"type": "code", "text": "טקסט"})

    def test_empty_text_has_no_blocks(self):
        self.assertEqual(parse("  \n\n"), [])

    def test_default_instructions_render_their_structure(self):
        blocks = parse(DEFAULT_INSTRUCTIONS)
        levels = [b["level"] for b in blocks if b["type"] == "heading"]
        self.assertEqual(levels.count(1), 5)
        self.assertEqual(levels.count(2), 4)
        self.assertEqual([len(b["items"]) for b in blocks if b["type"] == "list"], [3, 4, 5, 3, 4])


if __name__ == "__main__":
    unittest.main()
