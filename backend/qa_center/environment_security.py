from __future__ import annotations

import ipaddress
from typing import Iterable
import re

from rest_framework.exceptions import PermissionDenied, ValidationError

from room.models import AuditLog, ProjectMember


RFC1918_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]

BLOCKED_CIDR_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("169.254.169.254/32"),
]


def normalize_allowed_host(host: str) -> str:
    host = (host or "").strip()
    if not host:
        raise ValidationError("allowed_hosts 中不能有空值")
    if "://" in host or "/" in host or "?" in host or "#" in host:
        raise ValidationError("allowed_hosts 只允许 hostname，不允许 scheme/path/query/fragment")
    if "*" in host:
        raise ValidationError("allowed_hosts 第一阶段只支持 exact match，不允许通配符")
    if ":" in host:
        raise ValidationError("allowed_hosts 不允许端口")
    try:
        normalized = host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValidationError("allowed_hosts 含非法 hostname") from exc
    try:
        ipaddress.ip_address(normalized)
    except ValueError:
        pass
    else:
        raise ValidationError("allowed_hosts 只允许 hostname，不允许 IP")

    label_pattern = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    labels = normalized.split(".")
    if not all(label_pattern.match(label) for label in labels):
        raise ValidationError("allowed_hosts 含非法 hostname")
    return normalized


def validate_allowed_cidr(value: str) -> str:
    try:
        network = ipaddress.ip_network((value or "").strip(), strict=True)
    except ValueError as exc:
        raise ValidationError("allowed_cidrs 必须是合法 CIDR") from exc

    for blocked in BLOCKED_CIDR_NETWORKS:
        if network.version != blocked.version:
            continue
        if network.subnet_of(blocked) or blocked.subnet_of(network):
            raise ValidationError("allowed_cidrs 不允许 loopback/link-local/metadata/reserved 范围")

    if not any(
        network.version == allowed.version and network.subnet_of(allowed)
        for allowed in RFC1918_NETWORKS
    ):
        raise ValidationError("allowed_cidrs 第一阶段只允许 RFC1918 私网 CIDR")

    return str(network)


def ensure_project_admin(user, project) -> None:
    if not user or not user.is_authenticated:
        raise PermissionDenied("未认证用户不能修改 allowlist")
    if project.owner_id == user.id:
        return
    membership = (
        ProjectMember.objects.select_related("role")
        .filter(project=project, user=user)
        .first()
    )
    role_key = getattr(getattr(membership, "role", None), "key", "")
    if role_key in {"owner", "admin"}:
        return
    raise PermissionDenied("只有项目管理员可以修改 allowlist")


def write_allowlist_audit_log(
    *,
    user,
    environment,
    before_hosts: Iterable[str],
    after_hosts: Iterable[str],
    before_cidrs: Iterable[str],
    after_cidrs: Iterable[str],
    trace_id_or_request_id: str = "",
    client_ip: str | None = None,
    user_agent: str = "",
) -> None:
    AuditLog.objects.create(
        user=user,
        action="qa_env_allowlist_updated",
        resource_type="qa_test_environment",
        resource_id=str(environment.id),
        detail={
            "actor_id": user.id if user else None,
            "project_id": str(environment.project_id),
            "environment_id": environment.id,
            "trace_id_or_request_id": trace_id_or_request_id,
            "before": {
                "allowed_hosts": list(before_hosts),
                "allowed_cidrs": list(before_cidrs),
            },
            "after": {
                "allowed_hosts": list(after_hosts),
                "allowed_cidrs": list(after_cidrs),
            },
            "client_ip": client_ip,
        },
        ip_address=client_ip,
        user_agent=user_agent or "",
    )
