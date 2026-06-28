from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied


def project_access_q(project_path, user):
    """Return a Q object for resources attached to projects the user can access."""
    return (
        Q(**{f'{project_path}__owner': user}) |
        Q(**{f'{project_path}__members': user})
    )


def user_can_access_project(user, project):
    if not user or not user.is_authenticated or project is None:
        return False
    return project.owner_id == user.id or project.members.filter(id=user.id).exists()


def ensure_project_access(user, project):
    if not user_can_access_project(user, project):
        raise PermissionDenied('无权访问此项目')
    return project


def ensure_project_id_access(user, project_id):
    from room.models import Project

    project = get_object_or_404(Project, pk=project_id)
    return ensure_project_access(user, project)
