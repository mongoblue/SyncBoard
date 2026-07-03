import pytest

from bug_tracker.models import Bug


@pytest.mark.django_db
def test_create_bug_response_includes_id_and_title(auth_client, test_project):
    response = auth_client.post(
        "/api/bugs/",
        data={
            "project": str(test_project.id),
            "title": "Create response contract",
            "description": "Bug create should return detail payload.",
        },
        content_type="application/json",
    )

    assert response.status_code == 201

    bug = Bug.objects.get(title="Create response contract")
    assert response.data["id"] == bug.id
    assert response.data["title"] == bug.title
