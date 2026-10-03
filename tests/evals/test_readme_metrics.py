from pathlib import Path

from scripts.update_readme_metrics import update_readme


def test_readme_metrics_are_copied_from_reports(tmp_path: Path):
    readme = tmp_path / "README.md"
    fake = tmp_path / "REPORT.md"
    live = tmp_path / "LIVE_REPORT.md"
    readme.write_text("Before\n<!-- EVAL_METRICS_START -->\nold\n<!-- EVAL_METRICS_END -->\nAfter\n")
    fake.write_text("# Evaluation report\n\n| Metric | Result |\n| --- | ---: |\n"
                    "| Task success | 2/3 |\n\n## Scenarios\n")
    live.write_text("# Evaluation report\n\n| Metric | Result |\n| --- | ---: |\n"
                    "| Task success | 1/2 |\n\n## Scenarios\n")
    update_readme(readme, fake, live)
    text = readme.read_text()
    assert "| Task success | 2/3 |" in text
    assert "| Task success | 1/2 |" in text
    assert "Before" in text and "After" in text
    assert text.count("<!-- EVAL_METRICS_START -->") == 1
