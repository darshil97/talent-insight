"""The complete Deepgram Settings message, built server-side for one session."""

END_FUNCTION = "end_screening"
INTERVIEWER_MODEL_LABEL = "talent-insight-interviewer"


def greeting(job_title: str, minutes: int) -> str:
    return (
        f"Hello, I'm an AI screening assistant for the {job_title} role. "
        f"This conversation takes about {minutes} minutes. I'll ask a few job-related questions; "
        "a human recruiter reviews the conversation and makes every decision. "
        "You can ask to stop at any time, and a text option is available. Shall we begin?"
    )


def build_settings(settings, session_id: str, capability: str, job_title: str) -> dict:
    """Instructions stay server-side: the interviewer endpoint replaces any prompt it receives."""
    listen_version = "v2" if settings.voice_listen_model.startswith("flux") else "v1"
    return {
        "type": "Settings",
        "mip_opt_out": True,
        "audio": {
            "input": {"encoding": "linear16", "sample_rate": 16000},
            "output": {"encoding": "linear16", "sample_rate": 24000, "container": "none"},
        },
        "agent": {
            "listen": {
                "provider": {
                    "type": "deepgram",
                    "model": settings.voice_listen_model,
                    "version": listen_version,
                }
            },
            "think": {
                "provider": {"type": "open_ai", "model": INTERVIEWER_MODEL_LABEL},
                "endpoint": {
                    "url": (
                        f"{settings.voice_public_api_url}/screenings/{session_id}/chat/completions"
                    ),
                    "headers": {"authorization": f"Bearer {capability}"},
                },
                "prompt": "Server-managed screening interviewer.",
                "functions": [
                    {
                        "name": END_FUNCTION,
                        "description": "End the screening call after the closing message.",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            },
            "speak": {"provider": {"type": "deepgram", "model": settings.voice_speak_model}},
            "greeting": greeting(job_title, settings.voice_screening_seconds // 60),
        },
    }
