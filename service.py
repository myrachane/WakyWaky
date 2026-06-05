"""
service.py – WakyWaky AI Service
─────────────────────────────────
Responsibilities (ONLY):
  • Build the prompt from author + message + history
  • Communicate with Ollama
  • Return the generated reply string

No WhatsApp, Playwright, database, or logging code lives here.
"""

from __future__ import annotations

import requests

import config


# ─────────────────────────────────────────
#  System prompt
# ─────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are the owner of this WhatsApp account. "
    "Reply naturally. Keep replies short. Avoid sounding like AI. "
    "Avoid formal language. Use casual texting style. "
    "Use recent conversation history for context. "
    "Never mention being an AI."
)


# ─────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────

def generate_reply(
    author: str,
    message: str,
    history: list[dict],
) -> str:
    """
    Build a prompt from the conversation context and call Ollama.

    Parameters
    ----------
    author  : display name of the person who sent the message
    message : the latest incoming message text
    history : list of dicts with keys ``sender`` and ``message``,
              ordered oldest → newest (up to CONTEXT_MESSAGES entries)

    Returns
    -------
    str – the AI-generated reply (clean, stripped)
    """
    prompt = _build_prompt(author, message, history)
    reply = _call_ollama(prompt)
    return reply


# ─────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────

def _build_prompt(
    author: str,
    message: str,
    history: list[dict],
) -> str:
    """Assemble the full prompt string sent to the model."""

    sections: list[str] = [_SYSTEM_PROMPT, ""]

    if history:
        sections.append("Recent conversation history (oldest first):")
        for entry in history:
            sender_label = "Me" if entry["sender"] == "AI" else entry["sender"]
            sections.append(f"  {sender_label}: {entry['message']}")
        sections.append("")

    sections.append(f"New message from {author}:")
    sections.append(f"  {message}")
    sections.append("")
    sections.append("Reply (casual, short, natural — no AI talk):")

    return "\n".join(sections)


def _call_ollama(prompt: str) -> str:
    """POST to the Ollama generate endpoint and return the response text."""

    payload: dict = {
        "model": config.MODEL_NAME,
        "prompt": prompt,
        "stream": False,
    }

    try:
        response = requests.post(
            config.OLLAMA_URL,
            json=payload,
            timeout=config.OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        data: dict = response.json()
        reply: str = data.get("response", "").strip()
        if not reply:
            raise ValueError("Ollama returned an empty response.")
        return reply

    except requests.exceptions.ConnectionError as exc:
        raise ConnectionError(
            f"Cannot reach Ollama at {config.OLLAMA_URL}. "
            "Is Ollama running?"
        ) from exc

    except requests.exceptions.Timeout as exc:
        raise TimeoutError(
            f"Ollama request timed out after {config.OLLAMA_TIMEOUT}s."
        ) from exc

    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(
            f"Ollama HTTP error: {exc.response.status_code} – {exc.response.text}"
        ) from exc
