from evals.run import exit_code


def test_runner_fails_when_any_scenario_fails():
    assert exit_code([{"success": True}, {"success": True}]) == 0
    assert exit_code([{"success": True}, {"success": False}]) == 1
    assert exit_code([]) == 1  # running nothing is not a pass
