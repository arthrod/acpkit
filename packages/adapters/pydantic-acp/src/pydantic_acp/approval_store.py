from __future__ import annotations as _annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

from typing_extensions import TypeIs

from .session.state import AcpSessionContext, JsonValue

__all__ = (
    "ApprovalPolicy",
    "ApprovalPolicyStore",
    "PermissionOptionSet",
    "SessionMetadataApprovalPolicyStore",
)

ApprovalPolicy: TypeAlias = Literal["allow", "reject"]


def _is_approval_policy(value: JsonValue) -> TypeIs[ApprovalPolicy]:
    return value in {"allow", "reject"}


class ApprovalPolicyStore(Protocol):
    def get_policy(
        self,
        session: AcpSessionContext,
        policy_key: str,
    ) -> ApprovalPolicy | None: ...

    def set_policy(
        self,
        session: AcpSessionContext,
        policy_key: str,
        policy: ApprovalPolicy,
    ) -> None: ...

    def export_state(
        self,
        session: AcpSessionContext,
    ) -> dict[str, JsonValue] | None: ...


@dataclass(slots=True)
class SessionMetadataApprovalPolicyStore:
    metadata_key: str = "approval_policies"

    def get_policy(
        self,
        session: AcpSessionContext,
        policy_key: str,
    ) -> ApprovalPolicy | None:
        policy = self._policies(session).get(policy_key)
        if _is_approval_policy(policy):
            return policy
        return None

    def set_policy(
        self,
        session: AcpSessionContext,
        policy_key: str,
        policy: ApprovalPolicy,
    ) -> None:
        raw_policies = session.metadata.get(self.metadata_key)
        if not isinstance(raw_policies, dict):
            raw_policies = {}
            session.metadata[self.metadata_key] = raw_policies
        raw_policies[policy_key] = policy

    def export_state(
        self,
        session: AcpSessionContext,
    ) -> dict[str, JsonValue] | None:
        policies = self._policies(session)
        return dict(policies) if policies else None

    def _policies(self, session: AcpSessionContext) -> dict[str, JsonValue]:
        raw_policies = session.metadata.get(self.metadata_key)
        if isinstance(raw_policies, dict):
            return raw_policies
        return {}


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionOptionSet:
    allow_once_name: str = "Allow"
    reject_once_name: str = "Deny"
    allow_always_name: str = "Always Allow"
    reject_always_name: str = "Always Deny"
