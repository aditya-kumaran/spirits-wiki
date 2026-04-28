"""
Provider-agnostic LLM client supporting Groq (cloud) and Ollama (local).

Usage:
    from llm_client import create_llm_client

    client = create_llm_client()  # Reads LLM_PROVIDER from config
    response = client.chat(
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.0,
        max_tokens=300,
        json_mode=True,
    )
    print(response)  # The assistant's message content as a string
"""
import json
import time
import urllib.request
import urllib.error
from typing import Optional


class LLMClient:
    """Unified interface for LLM providers."""

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 300,
        json_mode: bool = False,
    ) -> Optional[str]:
        raise NotImplementedError


class GroqClient(LLMClient):
    """Groq cloud API client."""

    def __init__(self, api_key: str, model: str):
        from groq import Groq
        self.client = Groq(api_key=api_key)
        self.model = model

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 300,
        json_mode: bool = False,
    ) -> Optional[str]:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content


class OllamaClient(LLMClient):
    """Ollama local API client. No rate limits, no API keys needed."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._verify_connection()

    def _verify_connection(self):
        """Check that Ollama is running and the model is available."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                available = [m["name"] for m in data.get("models", [])]
                # Check if model is available (with or without :latest tag)
                model_base = self.model.split(":")[0]
                found = any(
                    m == self.model or m.startswith(model_base + ":")
                    for m in available
                )
                if not found:
                    print(f"  Warning: Model '{self.model}' not found in Ollama.")
                    print(f"  Available models: {', '.join(available) or '(none)'}")
                    print(f"  Run: ollama pull {self.model}")
                    raise RuntimeError(f"Model '{self.model}' not available in Ollama")
        except urllib.error.URLError:
            raise RuntimeError(
                "Cannot connect to Ollama at " + self.base_url + "\n"
                "Make sure Ollama is running: https://ollama.com\n"
                "Start it with: ollama serve"
            )

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 300,
        json_mode: bool = False,
    ) -> Optional[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                return data.get("message", {}).get("content")
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            print(f"  Ollama API error: {e.code} - {error_body}")
            return None
        except urllib.error.URLError as e:
            print(f"  Ollama connection error: {e}")
            return None


def create_llm_client(
    provider: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    groq_model: Optional[str] = None,
    ollama_model: Optional[str] = None,
    ollama_url: Optional[str] = None,
) -> LLMClient:
    """
    Create an LLM client based on provider setting.
    Falls back to config.py values if args not provided.
    """
    from config import (
        LLM_PROVIDER, GROQ_API_KEY, GROQ_MODEL,
        OLLAMA_MODEL, OLLAMA_URL,
    )

    provider = provider or LLM_PROVIDER
    provider = provider.lower().strip()

    if provider == "ollama":
        model = ollama_model or OLLAMA_MODEL
        url = ollama_url or OLLAMA_URL
        print(f"Using Ollama (model: {model}, url: {url})")
        return OllamaClient(model=model, base_url=url)
    elif provider == "groq":
        api_key = groq_api_key or GROQ_API_KEY
        model = groq_model or GROQ_MODEL
        if not api_key:
            raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        print(f"Using Groq (model: {model})")
        return GroqClient(api_key=api_key, model=model)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: '{provider}'. Use 'groq' or 'ollama'.")
