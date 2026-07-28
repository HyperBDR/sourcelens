"""Runtime-mode policies shared by the LensNode agent engine."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeMode:
    """Define mode-specific progress behavior."""

    name: str
    general_chat: bool = False
    execution_gates: bool = False

    def decorate_event(self, detail):
        """Return internal event details for this runtime mode."""

        return dict(detail or {})

    def emit_model_round(self, emit_event, suffix, round_number):
        """Keep legacy modes free of General Chat model-step events."""

        del emit_event, suffix, round_number


class GeneralChatMode(RuntimeMode):
    """Enable General Chat's user-visible hierarchical execution path."""

    def __init__(self):
        super().__init__(
            name="general_chat",
            general_chat=True,
            execution_gates=True,
        )

    def decorate_event(self, detail):
        """Mark events that may be projected into General Chat steps."""

        return {**super().decorate_event(detail), "runtime_scope": self.name}

    def emit_model_round(self, emit_event, suffix, round_number):
        """Emit one real model-round boundary for General Chat."""

        emit_event(
            f"model.round.{suffix}",
            {
                "invocation_id": f"model-round-{round_number}",
                "round": round_number,
            },
        )


class DocumentQAMode(RuntimeMode):
    """Preserve the existing document Q&A runtime behavior."""

    def __init__(self):
        super().__init__(name="document_qa")


class CodeAnalysisMode(RuntimeMode):
    """Preserve the existing code-analysis runtime behavior."""

    def __init__(self):
        super().__init__(name="code_analysis")


def runtime_mode_for(command):
    """Return the concrete runtime mode for one command."""

    task = str((command or {}).get("task") or "")
    if task == "general_chat":
        return GeneralChatMode()
    if task == "code_analysis":
        return CodeAnalysisMode()
    return DocumentQAMode()
