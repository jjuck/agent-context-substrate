from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _hermes_root() -> Path:
    return Path(os.environ.get("HERMES_AGENT_ROOT", Path.home() / ".hermes" / "hermes-agent"))


@pytest.mark.integration
def test_hermes_auxiliary_router_smoke_uses_real_auxiliary_client_shape() -> None:
    """Smoke the ACS adapter against the real Hermes auxiliary-client import surface.

    This does not call a live model. It imports Hermes' actual
    ``agent.auxiliary_client`` module, then stubs only the final ``call_llm``
    network seam so the smoke catches import/signature/response-shape drift.
    """

    hermes_root = _hermes_root()
    python = hermes_root / "venv" / "bin" / "python3"
    if not python.exists():
        pytest.skip(f"Hermes venv python not found: {python}")
    if not (hermes_root / "agent" / "auxiliary_client.py").exists():
        pytest.skip(f"Hermes auxiliary_client.py not found under: {hermes_root}")

    script = textwrap.dedent(
        f"""
        from __future__ import annotations

        import inspect
        import json
        import sys
        from types import SimpleNamespace

        sys.path.insert(0, {str(SRC)!r})
        sys.path.insert(0, {str(hermes_root)!r})

        import agent.auxiliary_client as auxiliary_client
        from agent_context_substrate.agent_llm_router import build_hermes_auxiliary_llm_router

        signature = inspect.signature(auxiliary_client.call_llm)
        for required_parameter in ("task", "messages", "temperature", "max_tokens", "extra_body"):
            assert required_parameter in signature.parameters, signature

        calls = []

        def fake_call_llm(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{{"summary": "ok", "mode": "agent-llm"}}')
                    )
                ]
            )

        router = build_hermes_auxiliary_llm_router(
            fake_call_llm,
            extract_content=auxiliary_client.extract_content_or_reasoning,
            path_policy="redact",
        )
        response = router(
            {{
                "kind": "micro",
                "schema_version": "micro_summary_v2",
                "evidence": {{
                    "session_id": "session-smoke",
                    "user_messages": [
                        {{
                            "message_id": 1,
                            "role": "user",
                            "content": "api_key=sk-smoke-secret and path /home/user/project/secret.py",
                        }}
                    ],
                }},
                "routing_hints": {{"budget": "cheap"}},
            }}
        )
        assert response == {{"summary": "ok", "mode": "agent-llm"}}
        assert len(calls) == 1
        call = calls[0]
        assert call["task"] == "agent_context_substrate_summary"
        assert call["messages"][0]["role"] == "system"
        assert "strict JSON" in call["messages"][0]["content"]
        assert call["extra_body"] == {{"response_format": {{"type": "json_object"}}}}
        serialized = json.dumps(call["messages"], ensure_ascii=False)
        assert "sk-smoke-secret" not in serialized
        assert "/home/user/project/secret.py" not in serialized
        assert "<REDACTED_SECRET>" in serialized
        assert "<REDACTED_LOCAL_PATH>" in serialized
        print(json.dumps({{"ok": True, "task": call["task"]}}))
        """
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{SRC}:{hermes_root}:{env.get('PYTHONPATH', '')}"

    result = subprocess.run(
        [str(python)],
        input=script,
        text=True,
        capture_output=True,
        check=False,
        timeout=45,
        env=env,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {
        "ok": True,
        "task": "agent_context_substrate_summary",
    }
