"""Context compaction policy for long-running LensNode investigations."""

from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.messages import HumanMessage, RemoveMessage

CONTINUATION_SUMMARY_PROMPT = (
    "You are compacting the context of an IN-PROGRESS investigation to "
    "free up space. The user's question has NOT been answered yet — you "
    "are still gathering evidence from the workspace and MUST keep working "
    "after this compaction. The notes below replace the older conversation "
    "history.\n\n"
    "The user's own messages are preserved verbatim outside this summary, "
    "so do NOT restate the question here — focus on distilling the evidence "
    "and the remaining work. Use these sections, writing 'None' where "
    "empty:\n\n"
    "## EVIDENCE GATHERED SO FAR\n"
    "Concrete findings already discovered, with file paths and the key "
    "facts/identifiers/values they contain. Be specific.\n\n"
    "## STILL TO DO\n"
    "What evidence is still missing to fully answer the question.\n\n"
    "Do NOT write a final answer here. Do NOT imply the task is complete "
    "or already answered. This is a working note to yourself so you can "
    "keep investigating, then produce the final answer in a later step.\n\n"
    "<messages>\n{messages}\n</messages>"
)


class LensSummarizationMiddleware(SummarizationMiddleware):
    """Compact older turns once the running context grows past a threshold.

    Deep investigations accumulate large tool outputs (file reads) that
    make every later LLM round re-send a growing transcript, and per-round
    latency scales with that context. Compacting the oldest turns into a
    summary keeps the recent working set verbatim while bounding context,
    cutting tail latency and the risk of context overflow. Re-queryable
    evidence (tool/file reads) can be searched again from the workspace if
    dropped; user-authored input cannot, so it is exempted from compaction
    (see _partition_messages and issue #60).
    """

    def _partition_messages(self, conversation_messages, cutoff_index):
        """Keep human input verbatim; summarize only re-queryable turns.

        The base split summarizes everything before the cutoff, which includes
        the user's original input. Content the user pasted into the chat is NOT
        re-queryable from the workspace, so summarizing it away loses it
        irrecoverably (issue #60). Move every HumanMessage out of the
        to-summarize set into the preserved set so the subject and the task
        survive compaction; summarize only the re-queryable tool/AI turns.
        """

        to_summarize = conversation_messages[:cutoff_index]
        preserved = conversation_messages[cutoff_index:]
        human_anchors = [
            message
            for message in to_summarize
            if isinstance(message, HumanMessage)
        ]
        if not human_anchors:
            return to_summarize, preserved
        non_human = [
            message
            for message in to_summarize
            if not isinstance(message, HumanMessage)
        ]
        # Anchors are clustered ahead of the preserved tail, not kept in their
        # original positions. The stream stays valid (no orphaned ToolMessages;
        # only HumanMessages move) and the user turns survive verbatim.
        return non_human, human_anchors + preserved

    def before_model(self, state, runtime):
        """Summarize on threshold and report what was compacted."""

        before_tokens = self.token_counter(state["messages"])
        result = super().before_model(state, runtime)
        emit = getattr(self, "_emit_event", None)
        if result is not None and emit is not None:
            kept = [
                message
                for message in result["messages"]
                if not isinstance(message, RemoveMessage)
            ]
            after_tokens = self.token_counter(kept)
            emit(
                "deepagents.summarization.compacted",
                {
                    "before_tokens": before_tokens,
                    "after_tokens": after_tokens,
                    "saved_tokens": max(before_tokens - after_tokens, 0),
                },
            )
        return result
