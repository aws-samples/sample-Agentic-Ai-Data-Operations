"""Shared utilities for the Agentic Data Onboarding platform.

Keep the public tracer imports lazy.  ``AgentTracer`` records cost-attribution
events and imports a utility module; eagerly importing ``script_tracer`` here
would make those two modules cyclic during package initialization.
"""

__all__ = ["ScriptTracer", "get_tracer"]


def __getattr__(name: str):
    if name in __all__:
        from shared.utils.script_tracer import ScriptTracer, get_tracer

        return {"ScriptTracer": ScriptTracer, "get_tracer": get_tracer}[name]
    raise AttributeError(name)
