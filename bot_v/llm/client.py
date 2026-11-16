"""LLM client used by every Bot V module.

Talks to either Ollama (``/api/...``) or any OpenAI-compatible server
(llama-server, LM Studio, vLLM, ...) depending on ``BOTV_LLM_BACKEND``.

Modules ask for a model by role (``"general"``, ``"coder"``, ``"vision"``,
``"embed"``); the role is resolved to a real model name from settings. A
literal model name also works and is passed through unchanged.
"""

from __future__ import annotations

import base64
import mimetypes
from typing import Any, Dict, List, Optional

import requests

from bot_v.config import settings as default_settings

ERROR_PREFIX = "[LLM ERROR]"


class LLMError(RuntimeError):
    """The LLM server could not be reached or returned an unusable answer."""


def is_error(text: str) -> bool:
    return isinstance(text, str) and text.startswith(ERROR_PREFIX)


class LLMClient:
    def __init__(
        self,
        host: Optional[str] = None,
        backend: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        models: Optional[Dict[str, str]] = None,
        session: Any = None,
    ):
        s = default_settings
        self.backend = (backend or s.llm_backend).lower()
        if self.backend not in ("ollama", "openai"):
            raise ValueError(f"Unknown LLM backend: {self.backend!r}")
        host = (host or s.llm_host).rstrip("/")
        if self.backend == "openai" and host.endswith("/v1"):
            host = host[: -len("/v1")]
        self.host = host
        self.api_key = s.llm_api_key if api_key is None else api_key
        self.timeout = timeout or s.llm_timeout
        self.models = dict(s.models if models is None else models)
        self.session = session or requests.Session()

    # ------------------------------------------------------------------ utils
    def resolve_model(self, model: str) -> str:
        return self.models.get(model, model)

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            res = self.session.post(
                f"{self.host}{path}", json=payload, headers=headers, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise LLMError(f"cannot reach {self.host}: {exc}") from exc
        if res.status_code >= 400:
            raise LLMError(f"{path} returned HTTP {res.status_code}: {res.text[:300]}")
        try:
            return res.json()
        except ValueError as exc:
            raise LLMError(f"{path} returned non-JSON: {res.text[:300]}") from exc

    # ------------------------------------------------------------ public API
    def chat(self, model: str, messages: List[Dict[str, Any]]) -> str:
        """Send chat messages and return the reply text. Raises LLMError."""
        name = self.resolve_model(model)
        if self.backend == "ollama":
            data = self._post(
                "/api/chat", {"model": name, "messages": messages, "stream": False}
            )
            content = (data.get("message") or {}).get("content")
        else:
            data = self._post("/v1/chat/completions", {"model": name, "messages": messages})
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                content = None
        if content is None:
            raise LLMError(f"no reply in response: {str(data)[:300]}")
        return content

    def query(self, model: str, prompt: str, system: Optional[str] = None) -> str:
        """Single prompt -> reply text.

        Never raises: on failure returns a string starting with ``[LLM ERROR]``
        (the contract the existing modules were written against).
        """
        messages: List[Dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            return self.chat(model, messages)
        except LLMError as exc:
            return f"{ERROR_PREFIX} {exc}"

    def embed(self, model: str, text: str) -> List[float]:
        """Return an embedding vector. Raises LLMError."""
        name = self.resolve_model(model)
        if self.backend == "ollama":
            data = self._post("/api/embed", {"model": name, "input": text})
            vectors = data.get("embeddings") or []
            vec = vectors[0] if vectors else None
        else:
            data = self._post("/v1/embeddings", {"model": name, "input": text})
            try:
                vec = data["data"][0]["embedding"]
            except (KeyError, IndexError, TypeError):
                vec = None
        if not vec:
            raise LLMError(f"no embedding in response: {str(data)[:300]}")
        return [float(x) for x in vec]

    def query_image(self, model: str, prompt: str, image_path: str) -> str:
        """Ask a vision model about a local image. Never raises (see query)."""
        try:
            with open(image_path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("ascii")
        except OSError as exc:
            return f"{ERROR_PREFIX} cannot read image {image_path}: {exc}"

        if self.backend == "ollama":
            message = {"role": "user", "content": prompt, "images": [b64]}
        else:
            mime = mimetypes.guess_type(image_path)[0] or "image/png"
            message = {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }
        try:
            return self.chat(model, [message])
        except LLMError as exc:
            return f"{ERROR_PREFIX} {exc}"
