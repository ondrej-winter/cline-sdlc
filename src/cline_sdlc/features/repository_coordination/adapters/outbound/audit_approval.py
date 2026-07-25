"""Adapter mapping repository invocation approvals to the run-audit API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cline_sdlc.features.run_audit.application.dtos.run_audit import InvocationApprovalRecord

if TYPE_CHECKING:
    from cline_sdlc.features.repository_coordination.application.dtos.reconciliation import InvocationApproval
    from cline_sdlc.features.run_audit.application.use_cases.record_invocation_approval import RecordInvocationApproval


class RunAuditInvocationApprovalRecorder:
    """Map an approved invocation into immutable run-audit persistence."""

    def __init__(self, recorder: RecordInvocationApproval) -> None:
        self._recorder = recorder

    def record_approval(self, repository_root: str, approval: InvocationApproval) -> str:
        """Persist approval and raise when the audit boundary rejects it."""
        result = self._recorder.execute(
            repository_root,
            InvocationApprovalRecord(
                schema_version=1,
                run_id=approval.run_id,
                profile=approval.profile,
                starting_head=approval.starting_head,
                approved_at=approval.approved_at.isoformat().replace("+00:00", "Z"),
                specification_digest=approval.specification_digest,
                material_digest=approval.material_digest,
                remediation_envelope_applicable=approval.remediation_envelope_applicable,
            ),
        )
        if not result.recorded or result.approval_path is None:
            evidence = result.blocker.summary if result.blocker is not None else "unknown audit failure"
            raise ValueError(evidence)
        return result.approval_path
