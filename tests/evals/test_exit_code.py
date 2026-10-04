from evals.run import exit_code, report_path


def test_runner_fails_when_any_scenario_fails():
    assert exit_code([{"success": True}, {"success": True}]) == 0
    assert exit_code([{"success": True}, {"success": False}]) == 1
    assert exit_code([]) == 1  # running nothing is not a pass


def test_report_path_keeps_bare_names_in_evals_and_honours_paths(tmp_path):
    assert report_path("X.md").parent.name == "evals"
    assert report_path(str(tmp_path / "x.md")) == tmp_path / "x.md"
