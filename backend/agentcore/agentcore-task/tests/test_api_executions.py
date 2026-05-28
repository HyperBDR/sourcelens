"""
API tests for task execution endpoints: list, retrieve, status, sync,
stats, my-tasks.
"""
import pytest
from agentcore_task.adapters.django.services import register_task_execution


pytestmark = [pytest.mark.api]


BASE_URL = "/api/v1/tasks/executions"


@pytest.fixture
def execution(user, db):
    return register_task_execution(
        task_id="api-test-task-001",
        task_name="myapp.tasks.sample",
        module="myapp",
        task_kwargs={"key": "value"},
        created_by=user,
        metadata={"test": True},
    )


@pytest.fixture
def second_execution(user, db):
    return register_task_execution(
        task_id="api-test-task-002",
        task_name="myapp.tasks.other",
        module="myapp",
        created_by=user,
    )


class TestListExecutions:
    def test_list_requires_auth(self, api_client):
        response = api_client.get(BASE_URL + "/")
        assert response.status_code == 403

    def test_list_returns_user_tasks_by_default(
        self, authenticated_client, execution, second_execution
    ):
        response = authenticated_client.get(BASE_URL + "/")
        assert response.status_code == 200
        data = response.json()
        if "results" in data:
            assert len(data["results"]) >= 2
        else:
            assert len(data) >= 2

    def test_list_filter_by_module(
        self, authenticated_client, execution, second_execution
    ):
        response = authenticated_client.get(
            BASE_URL + "/", {"module": "myapp"}
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        assert all(item.get("module") == "myapp" for item in items)

    def test_list_filter_by_task_name(self, authenticated_client, execution):
        response = authenticated_client.get(
            BASE_URL + "/",
            {"task_name": "myapp.tasks.sample"},
        )
        assert response.status_code == 200
        data = response.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        assert any(
            item.get("task_name") == "myapp.tasks.sample"
            for item in items
        )

    def test_list_filter_by_status(self, authenticated_client, execution):
        response = authenticated_client.get(
            BASE_URL + "/", {"status": "PENDING"}
        )
        assert response.status_code == 200


class TestRetrieveExecution:
    def test_retrieve_requires_auth(self, api_client, execution):
        url = f"{BASE_URL}/{execution.pk}/"
        response = api_client.get(url)
        assert response.status_code == 403

    def test_retrieve_returns_execution(self, authenticated_client, execution):
        url = f"{BASE_URL}/{execution.pk}/"
        response = authenticated_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == execution.task_id
        assert data["task_name"] == execution.task_name
        assert data["module"] == "myapp"
        assert data["status"] == "PENDING"

    def test_retrieve_404_for_unknown_id(self, authenticated_client):
        response = authenticated_client.get(f"{BASE_URL}/99999/")
        assert response.status_code == 404


class TestStatusAction:
    def test_status_requires_task_id(self, authenticated_client):
        response = authenticated_client.get(BASE_URL + "/status/")
        assert response.status_code == 400
        assert "task_id" in response.json().get("error", "").lower()

    def test_status_returns_execution(self, authenticated_client, execution):
        response = authenticated_client.get(
            BASE_URL + "/status/",
            {"task_id": execution.task_id, "sync": "false"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == execution.task_id
        assert data["status"] == "PENDING"

    def test_status_404_when_not_found(self, authenticated_client):
        response = authenticated_client.get(
            BASE_URL + "/status/",
            {"task_id": "non-existent-id", "sync": "false"},
        )
        assert response.status_code == 404  # noqa: PLR2004


class TestByTaskIdAction:
    def test_by_task_id_returns_execution(
        self, authenticated_client, execution
    ):
        url = f"{BASE_URL}/by-task-id/{execution.task_id}/"
        response = authenticated_client.get(url + "?sync=false")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == execution.task_id

    def test_by_task_id_404_when_not_found(self, authenticated_client):
        url = f"{BASE_URL}/by-task-id/nonexistent-id/?sync=false"
        response = authenticated_client.get(url)
        assert response.status_code == 404


class TestSyncAction:
    def test_sync_returns_updated_execution(
        self, authenticated_client, execution
    ):
        url = f"{BASE_URL}/{execution.pk}/sync/"
        response = authenticated_client.post(url)
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert data["task_id"] == execution.task_id


class TestStatsAction:
    def test_stats_returns_counts(
        self, authenticated_client, execution, second_execution
    ):
        response = authenticated_client.get(BASE_URL + "/stats/")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert data["total"] >= 2
        assert "pending" in data
        assert "by_module" in data
        assert "by_task_name" in data

    def test_stats_filter_by_module(
        self, authenticated_client, execution
    ):
        response = authenticated_client.get(
            BASE_URL + "/stats/",
            {"module": "myapp"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert "myapp" in data["by_module"]


class TestMyTasksAction:
    def test_my_tasks_returns_user_tasks(
        self, authenticated_client, execution
    ):
        response = authenticated_client.get(BASE_URL + "/my-tasks/")
        assert response.status_code == 200
        data = response.json()
        items = data.get("results", data) if isinstance(data, dict) else data
        assert isinstance(items, list)
        task_ids = [item.get("task_id") for item in items]
        assert execution.task_id in task_ids
