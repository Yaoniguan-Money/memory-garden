"""FastAPI helper — Memory Garden as a FastAPI dependency.

Design source: planning Layer 4, Section 9.

Usage::

    from fastapi import FastAPI, Depends
    from memory_garden.sdk import MemoryGarden
    from memory_garden.integrations.adapters.fastapi import GardenFastAPI

    garden = MemoryGarden.local("./my_garden")
    garden_fastapi = GardenFastAPI(garden=garden)
    app = FastAPI()

    @app.post("/chat")
    async def chat(
        request: dict,
        ctx: dict = Depends(garden_fastapi.before_request),
    ):
        # ctx["brief"] contains the Garden Brief
        # ctx["session_id"] is the current session
        reply = await your_llm(request["message"], ctx["brief"])
        garden_fastapi.after_request(ctx, reply)
        return {"reply": reply}

Zero hard dependency on ``fastapi``.
"""

from __future__ import annotations

from typing import Any


class GardenFastAPI:
    """Memory Garden as a FastAPI dependency injection helper.

    Does NOT take over the FastAPI app.  Provides ``before_request()``
    and ``after_request()`` as composable helpers.
    """

    def __init__(self, *, garden: Any, providers: Any | None = None) -> None:
        self._garden = garden
        from memory_garden.integrations.adapters._cognitive_brief import resolve_provider_registry
        from memory_garden.skill import GardenSkill

        self._skill: GardenSkill = garden.as_skill()
        self._providers = resolve_provider_registry(garden, providers)
        if self._providers is not None:
            self._skill.configure_providers(self._providers)

    @property
    def skill(self) -> Any:
        return self._skill

    @property
    def garden(self) -> Any:
        return self._garden

    def before_request(
        self,
        request: dict | None = None,
        user_message: str | None = None,
    ) -> dict[str, Any]:
        """FastAPI dependency: inject garden context before handling a request.

        Usage as a FastAPI dependency::

            @app.post("/chat")
            async def chat(req: ChatRequest, ctx: dict = Depends(garden_fastapi.before_request)):
                ...
        """
        msg = user_message or ""
        if request and not msg:
            msg = str(request.get("message", request.get("content", "")))

        from memory_garden.integrations.adapters._cognitive_brief import build_cognitive_skill_context

        ctx = build_cognitive_skill_context(
            garden=self._garden,
            skill=self._skill,
            providers=self._providers,
            user_message=msg,
            metadata={"adapter": "fastapi", "source_role": "user"},
            max_candidates=5,
        )
        if ctx is None:
            ctx = self._skill.before(msg)
        return {
            "brief": ctx.brief_text,
            "session_id": ctx.session_id,
            "messages": ctx.messages,
            "user_message": msg,
        }

    async def before_request_async(
        self,
        request: dict | None = None,
        user_message: str | None = None,
    ) -> dict[str, Any]:
        """Async variant for FastAPI async endpoints."""
        return self.before_request(request=request, user_message=user_message)

    def after_request(self, ctx: dict, assistant_reply: str) -> None:
        """Observe the assistant reply after the request is handled."""
        self._skill.after(
            str(ctx.get("user_message", "[FastAPI request]")),
            assistant_reply,
        )

    def open_session(self, *, metadata: dict | None = None) -> str:
        return self._skill.open(metadata=metadata)

    def close_session(self) -> Any:
        return self._skill.close()

    @property
    def health(self) -> Any:
        return self._garden.health()
