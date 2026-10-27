from finance_automation import page


def test_page_is_one_file_that_opens_from_disk(tmp_path):
    text = page.build(tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<h1>" in text
    assert 'src="http' not in text and "<script" not in text


def test_markdown_tables_and_links():
    out = page.md("| a | b |\n|---|---:|\n| **x** | [y](z.md) |", "docs")
    assert "<strong>x</strong>" in out and "class=r" in out
    assert f'href="{page.REPO}/blob/main/docs/z.md"' in out
