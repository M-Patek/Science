from science_repo.campaign import validate_campaign


def campaign(tasks):
    return {
        "schema_version": 1,
        "id": "test-campaign",
        "title": "Test",
        "objective": "Test DAG behavior",
        "status": "draft",
        "owner": "tests",
        "tasks": tasks,
    }


def task(task_id, dependencies):
    return {"id": task_id, "depends_on": dependencies, "write_scope": [f"work/{task_id}/"]}


def test_campaign_accepts_dag():
    assert validate_campaign(campaign([task("a", []), task("b", ["a"])])) == []


def test_campaign_rejects_cycle():
    errors = validate_campaign(campaign([task("a", ["b"]), task("b", ["a"])]))
    assert any("dependency cycle" in error for error in errors)


def test_campaign_rejects_unknown_dependency():
    errors = validate_campaign(campaign([task("a", ["missing"])]))
    assert any("unknown dependencies" in error for error in errors)
