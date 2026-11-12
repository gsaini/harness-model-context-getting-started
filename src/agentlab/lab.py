"""Ready-made agents for the lessons and the benchmark: one function, and named harness versions."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from agentlab import ROOT
from agentlab.context import Context, FileMemory, KeywordRetriever, remember_tool
from agentlab.harness import Agent, Middleware, Model
from agentlab.middleware import Compaction, ProtectPaths, Tracer
from agentlab.models import get_model
from agentlab.tools import Workspace, file_tools

COMPANY = ROOT / "fixtures" / "company"  # AGENTS.md and a small handbook: the "your organization" part


def company_context(
    *,
    instructions: bool = True,
    knowledge: bool = True,
    memory: FileMemory | None = None,
    extra_knowledge: Sequence[Path] = (),
    **retriever_options: object,
) -> Context:
    return Context(
        instructions=(COMPANY / "AGENTS.md").read_text(encoding="utf-8") if instructions else None,
        knowledge=KeywordRetriever(COMPANY / "handbook", *extra_knowledge, **retriever_options) if knowledge else None,
        memory=memory,
    )


def build_agent(
    model: Model,
    workspace: Path,
    *,
    context: Context | None = None,
    compaction: str | None = None,
    protect: Sequence[str] = (),
    tracer: Tracer | None = None,
    edit: str | None = None,
    memory: FileMemory | None = None,
    extra_middleware: Sequence[Middleware] = (),
    max_steps: int = 20,
) -> Agent:
    """Assemble an agent from the three pillars: a model, a context, and a harness (tools + middleware)."""
    tools = file_tools(Workspace(workspace), edit or model.native_edit_tool)
    if memory is not None:
        tools.append(remember_tool(memory))
    middleware: list[Middleware] = [tracer] if tracer else []  # outermost, so it sees blocked calls too
    if protect:
        middleware.append(ProtectPaths(protect))
    if compaction:
        middleware.append(Compaction(compaction))
    middleware.extend(extra_middleware)
    return Agent(model=model, tools=tools, context=context, middleware=middleware, max_steps=max_steps)


@dataclass(frozen=True)
class Candidate:
    """A named harness configuration: one column of the scoreboard."""

    name: str
    label: str
    model: str = "scripted-careful"
    context: bool = False
    compaction: str | None = None
    protect: tuple[str, ...] = ()
    edit: str | None = None
    extra_knowledge: tuple[Path, ...] = ()
    context_factory: Callable[[], Context] | None = None  # replaces the company context when set

    def build(self, workspace: Path, *, tracer: Tracer | None = None, model: Model | None = None) -> Agent:
        if self.context_factory:
            context = self.context_factory()
        else:
            context = company_context(extra_knowledge=self.extra_knowledge) if self.context else None
        return build_agent(
            model or get_model(self.model),
            workspace,
            context=context,
            compaction=self.compaction,
            protect=self.protect,
            tracer=tracer,
            edit=self.edit,
        )

    def but(self, name: str, label: str, **changes: object) -> Candidate:
        return replace(self, name=name, label=label, **changes)


V0 = Candidate("v0", "the bare loop and four file tools")
V1 = V0.but("v1", "+ context (instructions, handbook)", context=True)
V2 = V1.but("v2", "+ compaction (summarize)", compaction="summarize")
V3 = V2.but("v3", "+ policy guard (.env)", protect=(".env",))
CANDIDATES = {c.name: c for c in (V0, V1, V2, V3)}
