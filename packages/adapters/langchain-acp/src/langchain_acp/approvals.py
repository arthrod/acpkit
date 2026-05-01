from __future__ import annotations as _annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from acp.exceptions import RequestError
from acp.interfaces import Client as AcpClient
from acp.schema import PermissionOption
from typing_extensions import TypeIs

from .approval_store import (
    ApprovalPolicy,
    ApprovalPolicyStore,
    PermissionOptionSet,
    SessionMetadataApprovalPolicyStore,
)
from .permission_presentation import (
    DefaultPermissionToolCallBuilder,
    PermissionRequestContext,
    PermissionToolCallBuilder,
)
from .projection import ProjectionMap, ToolClassifier
from .session.state import AcpSessionContext

__all__ = (
    "ApprovalBridge",
    "ApprovalDecision",
    "NativeApprovalBridge",
    "ProjectionAwareApprovalBridge",
    "supports_projection_aware_approval_bridge",
)


@dataclass(slots=True, frozen=True, kw_only=True)
class ApprovalDecision:
    decisions: list[dict[str, Any]]
    cancelled: bool = False


class ApprovalBridge(Protocol):
    async def resolve_action_requests(
        self,
        *,
        client: AcpClient,
        session: AcpSessionContext,
        action_requests: list[dict[str, Any]],
        review_configs: list[dict[str, Any]],
        classifier: ToolClassifier,
    ) -> ApprovalDecision: ...


class ProjectionAwareApprovalBridge(Protocol):
    async def resolve_action_requests(
        self,
        *,
        client: AcpClient,
        session: AcpSessionContext,
        action_requests: list[dict[str, Any]],
        review_configs: list[dict[str, Any]],
        classifier: ToolClassifier,
        projection_map: ProjectionMap | None,
    ) -> ApprovalDecision: ...


def supports_projection_aware_approval_bridge(
    bridge: ApprovalBridge | ProjectionAwareApprovalBridge | None,
) -> TypeIs[ProjectionAwareApprovalBridge]:
    if bridge is None:
        return False
    return hasattr(bridge, "_supports_projection_aware_approval_bridge")


@dataclass(slots=True, kw_only=True)
class NativeApprovalBridge:
    enable_persistent_choices: bool = False
    option_set: PermissionOptionSet = field(default_factory=PermissionOptionSet)
    policy_store: ApprovalPolicyStore = field(default_factory=SessionMetadataApprovalPolicyStore)
    tool_call_builder: PermissionToolCallBuilder = field(
        default_factory=DefaultPermissionToolCallBuilder
    )
    _supports_projection_aware_approval_bridge: bool = field(
        default=True,
        init=False,
        repr=False,
    )

    async def resolve_action_requests(
        self,
        *,
        client: AcpClient,
        session: AcpSessionContext,
        action_requests: list[dict[str, Any]],
        review_configs: list[dict[str, Any]],
        classifier: ToolClassifier,
        projection_map: ProjectionMap | None = None,
    ) -> ApprovalDecision:
        decisions: list[dict[str, Any]] = []
        config_by_action = {
            config.get("action_name"): config
            for config in review_configs
            if isinstance(config, dict)
        }
        for action_request in action_requests:
            if not isinstance(action_request, dict):
                raise RequestError.invalid_request({"action_request": action_request})
            tool_name = action_request.get("name")
            tool_args = action_request.get("args", {})
            if not isinstance(tool_name, str) or not isinstance(tool_args, dict):
                raise RequestError.invalid_request({"action_request": action_request})
            policy_key = classifier.approval_policy_key(tool_name, tool_args)
            remembered_policy = (
                self.policy_store.get_policy(session, policy_key)
                if self.enable_persistent_choices
                else None
            )
            if remembered_policy == "allow":
                decisions.append({"type": "approve"})
                continue
            if remembered_policy == "reject":
                decisions.append({"type": "reject"})
                continue
            review_config = config_by_action.get(tool_name, {})
            allowed_decisions = review_config.get("allowed_decisions", ["approve", "reject"])
            if "edit" in allowed_decisions and set(allowed_decisions) == {"edit"}:
                raise RequestError.invalid_request(
                    {"reason": "ACP permission prompts cannot collect edited tool arguments."}
                )
            permission = await client.request_permission(
                session_id=session.session_id,
                options=self._build_permission_options(),
                tool_call=self.tool_call_builder.build_tool_call_update(
                    PermissionRequestContext(
                        session=session,
                        tool_call_id=self._tool_call_id(action_request, tool_name),
                        tool_name=tool_name,
                        raw_input=tool_args,
                        cwd=session.cwd,
                        classifier=classifier,
                        projection_map=projection_map,
                    )
                ),
            )
            outcome = permission.outcome
            if outcome.outcome == "cancelled":
                return ApprovalDecision(decisions=decisions, cancelled=True)
            option_id = getattr(outcome, "option_id", None)
            if option_id == "allow_once":
                decisions.append({"type": "approve"})
                continue
            if option_id == "reject_once":
                decisions.append({"type": "reject"})
                continue
            if option_id == "allow_always":
                self._remember_policy(session, policy_key, "allow")
                decisions.append({"type": "approve"})
                continue
            if option_id == "reject_always":
                self._remember_policy(session, policy_key, "reject")
                decisions.append({"type": "reject"})
                continue
            raise RequestError.invalid_request({"optionId": option_id})
        return ApprovalDecision(decisions=decisions)

    def _build_permission_options(self) -> list[PermissionOption]:
        options = [
            PermissionOption(
                option_id="allow_once",
                name=self.option_set.allow_once_name,
                kind="allow_once",
            ),
            PermissionOption(
                option_id="reject_once",
                name=self.option_set.reject_once_name,
                kind="reject_once",
            ),
        ]
        if self.enable_persistent_choices:
            options.extend(
                [
                    PermissionOption(
                        option_id="allow_always",
                        name=self.option_set.allow_always_name,
                        kind="allow_always",
                    ),
                    PermissionOption(
                        option_id="reject_always",
                        name=self.option_set.reject_always_name,
                        kind="reject_always",
                    ),
                ]
            )
        return options

    def _remember_policy(
        self,
        session: AcpSessionContext,
        policy_key: str,
        policy: ApprovalPolicy,
    ) -> None:
        if not self.enable_persistent_choices:
            return
        self.policy_store.set_policy(session, policy_key, policy)

    def _tool_call_id(self, action_request: dict[str, Any], tool_name: str) -> str:
        action_id = action_request.get("id")
        if isinstance(action_id, str) and action_id:
            return action_id
        return f"hitl:{tool_name}"
