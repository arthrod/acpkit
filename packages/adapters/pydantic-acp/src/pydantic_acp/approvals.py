from __future__ import annotations as _annotations

from dataclasses import dataclass, field
from inspect import Parameter, signature
from typing import Protocol

from acp.exceptions import RequestError
from acp.interfaces import Client as AcpClient
from acp.schema import PermissionOption
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults, ToolApproved, ToolDenied
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
from .session.state import AcpSessionContext, JsonValue

__all__ = (
    "ApprovalBridge",
    "ApprovalPolicy",
    "ApprovalPolicyStore",
    "ApprovalResolution",
    "NativeApprovalBridge",
    "PermissionOptionSet",
    "ProjectionAwareApprovalBridge",
    "SessionMetadataApprovalPolicyStore",
    "supports_projection_aware_approval_bridge",
)


@dataclass(slots=True, frozen=True, kw_only=True)
class ApprovalResolution:
    deferred_tool_results: DeferredToolResults
    cancelled: bool = False
    cancelled_tool_call: ToolCallPart | None = None


class ApprovalBridge(Protocol):
    async def resolve_deferred_approvals(
        self,
        *,
        client: AcpClient,
        session: AcpSessionContext,
        requests: DeferredToolRequests,
        classifier: ToolClassifier,
    ) -> ApprovalResolution: ...


class ProjectionAwareApprovalBridge(Protocol):
    async def resolve_deferred_approvals(
        self,
        *,
        client: AcpClient,
        session: AcpSessionContext,
        requests: DeferredToolRequests,
        classifier: ToolClassifier,
        projection_map: ProjectionMap | None = None,
    ) -> ApprovalResolution: ...


def supports_projection_aware_approval_bridge(
    value: object,
) -> TypeIs[ProjectionAwareApprovalBridge]:
    resolver = getattr(value, "resolve_deferred_approvals", None)
    if not callable(resolver):
        return False
    try:
        resolver_signature = signature(resolver)
    except (TypeError, ValueError):
        return False
    parameters = resolver_signature.parameters
    if "projection_map" in parameters:
        return True
    return any(parameter.kind is Parameter.VAR_KEYWORD for parameter in parameters.values())


@dataclass(slots=True, kw_only=True)
class NativeApprovalBridge:
    enable_persistent_choices: bool = False
    tool_call_builder: PermissionToolCallBuilder = field(
        default_factory=DefaultPermissionToolCallBuilder
    )
    policy_store: ApprovalPolicyStore = field(default_factory=SessionMetadataApprovalPolicyStore)
    option_set: PermissionOptionSet = field(default_factory=PermissionOptionSet)

    async def resolve_deferred_approvals(
        self,
        *,
        client: AcpClient,
        session: AcpSessionContext,
        requests: DeferredToolRequests,
        classifier: ToolClassifier,
        projection_map: ProjectionMap | None = None,
    ) -> ApprovalResolution:
        deferred_results = DeferredToolResults(metadata=dict(requests.metadata))
        for tool_call in requests.approvals:
            raw_input = tool_call.args_as_dict()
            approval_policy_key = classifier.approval_policy_key(tool_call.tool_name, raw_input)
            remembered_policy = self._get_remembered_policy(session, approval_policy_key)
            if remembered_policy is not None:
                deferred_results.approvals[tool_call.tool_call_id] = self._policy_to_result(
                    remembered_policy
                )
                continue

            permission_response = await client.request_permission(
                options=self._build_permission_options(),
                session_id=session.session_id,
                tool_call=self.tool_call_builder.build_tool_call_update(
                    PermissionRequestContext(
                        session=session,
                        tool_call=tool_call,
                        raw_input=dict(raw_input),
                        cwd=session.cwd,
                        classifier=classifier,
                        projection_map=projection_map,
                    )
                ),
            )
            outcome = permission_response.outcome
            if outcome.outcome == "cancelled":
                return ApprovalResolution(
                    deferred_tool_results=deferred_results,
                    cancelled=True,
                    cancelled_tool_call=tool_call,
                )

            selected_result = self._selected_option_to_result(outcome.option_id)
            if selected_result is None:
                raise RequestError.invalid_request({"optionId": outcome.option_id})
            self._remember_policy(
                session=session,
                approval_policy_key=approval_policy_key,
                option_id=outcome.option_id,
            )
            deferred_results.approvals[tool_call.tool_call_id] = selected_result

        return ApprovalResolution(deferred_tool_results=deferred_results)

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
        if not self.enable_persistent_choices:
            return options
        return [
            options[0],
            PermissionOption(
                option_id="allow_always",
                name=self.option_set.allow_always_name,
                kind="allow_always",
            ),
            options[1],
            PermissionOption(
                option_id="reject_always",
                name=self.option_set.reject_always_name,
                kind="reject_always",
            ),
        ]

    def _selected_option_to_result(
        self,
        option_id: str,
    ) -> ToolApproved | ToolDenied | None:
        if option_id in {"allow_once", "allow_always"}:
            return ToolApproved()
        if option_id in {"reject_once", "reject_always"}:
            return ToolDenied()
        return None

    def _remember_policy(
        self,
        *,
        session: AcpSessionContext,
        approval_policy_key: str,
        option_id: str,
    ) -> None:
        if not self.enable_persistent_choices:
            return
        if option_id == "allow_always":
            self._set_remembered_policy(
                session,
                approval_policy_key=approval_policy_key,
                policy="allow",
            )
        elif option_id == "reject_always":
            self._set_remembered_policy(
                session,
                approval_policy_key=approval_policy_key,
                policy="reject",
            )

    def _get_remembered_policy(
        self,
        session: AcpSessionContext,
        approval_policy_key: str,
    ) -> ApprovalPolicy | None:
        if not self.enable_persistent_choices:
            return None
        return self.policy_store.get_policy(session, approval_policy_key)

    def _set_remembered_policy(
        self,
        session: AcpSessionContext,
        *,
        approval_policy_key: str,
        policy: ApprovalPolicy,
    ) -> None:
        self.policy_store.set_policy(session, approval_policy_key, policy)

    def _approval_policies(self, session: AcpSessionContext) -> dict[str, JsonValue]:
        exported = self.policy_store.export_state(session)
        return exported if exported is not None else {}

    def _policy_to_result(self, policy: ApprovalPolicy) -> ToolApproved | ToolDenied:
        if policy == "allow":
            return ToolApproved()
        return ToolDenied()
