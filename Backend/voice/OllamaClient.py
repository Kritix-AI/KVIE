"""
OllamaClient.py — Local Ollama API Client
Wraps local Ollama server (http://localhost:11434) for phi3:mini and other local models.
"""
import requests
import json
import os
from typing import Optional, List, Dict, Any
from dotenv import dotenv_values

env = dotenv_values(".env")

OLLAMA_LOCAL_URL = env.get("OLLAMA_LOCAL_URL", "http://localhost:11434/api")
OLLAMA_DEFAULT_MODEL = env.get("OLLAMA_DEFAULT_MODEL", "phi3:mini")
OLLAMA_TIMEOUT = int(env.get("OLLAMA_TIMEOUT", "60"))
# Keep the local model's KV-cache bounded.  An inherited 1M-token context can
# make even phi3:mini request tens of GB during llama-server startup.
OLLAMA_CONTEXT_LENGTH = int(env.get("OLLAMA_CONTEXT_LENGTH", "4096"))


class OllamaLocalClient:
    """Client for local Ollama server API"""

    def __init__(self, base_url: str = None, default_model: str = None):
        self.base_url = (base_url or OLLAMA_LOCAL_URL).rstrip("/")
        self.default_model = default_model or OLLAMA_DEFAULT_MODEL
        self.session = requests.Session()

    def _is_available(self) -> bool:
        """Check if Ollama server is running"""
        try:
            resp = self.session.get(f"{self.base_url}/tags", timeout=3)
            return resp.status_code == 200
        except:
            return False

    def list_models(self) -> List[str]:
        """List available models on local Ollama"""
        try:
            resp = self.session.get(f"{self.base_url}/tags", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return [m.get("name", "") for m in data.get("models", [])]
            return []
        except:
            return []

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        system: str = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        stream: bool = False,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Send a chat completion request to local Ollama.

        Args:
            messages: List of {"role": "user/assistant/system", "content": "..."}
            model: Model name (default: phi3:mini)
            system: System prompt override
            temperature: Sampling temperature (0-2)
            max_tokens: Max response tokens
            stream: Whether to stream response

        Returns:
            (response_text, error) tuple
        """
        target_model = model or self.default_model

        # Build payload
        def _make_payload(m: str) -> Dict[str, Any]:
            p: Dict[str, Any] = {
                "model": m,
                "messages": messages,
                "stream": stream,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "num_ctx": OLLAMA_CONTEXT_LENGTH,
                },
            }
            if system:
                p["messages"] = [
                    {"role": "system", "content": system},
                    *[msg for msg in messages if msg.get("role") != "system"],
                ]
            return p

        try:
            resp = self.session.post(
                f"{self.base_url}/chat",
                json=_make_payload(target_model),
                timeout=OLLAMA_TIMEOUT,
            )

            # If model not found (404), try available models from /tags
            if resp.status_code == 404 or (resp.status_code != 200 and "not found" in resp.text.lower()):
                avail = self.list_models()
                if avail and avail[0] != target_model:
                    target_model = avail[0]
                    self.default_model = target_model
                    resp = self.session.post(
                        f"{self.base_url}/chat",
                        json=_make_payload(target_model),
                        timeout=OLLAMA_TIMEOUT,
                    )

            if resp.status_code != 200:
                return None, f"Ollama HTTP {resp.status_code}: {resp.text[:200]}"

            data = resp.json()
            message = data.get("message", {})
            content = message.get("content", "")

            return content.strip() if content else "", None

        except requests.exceptions.ConnectionError:
            return None, "Ollama server not running (localhost:11434)"
        except requests.exceptions.Timeout:
            return None, f"Ollama timed out after {OLLAMA_TIMEOUT}s"
        except Exception as e:
            return None, f"Ollama error: {str(e)}"

    def generate(
        self,
        prompt: str,
        model: str = None,
        system: str = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Simple text generation (single prompt → single response).

        Args:
            prompt: The user prompt
            model: Model name (default: phi3:mini)
            system: System prompt
            temperature: Sampling temperature
            max_tokens: Max response tokens

        Returns:
            (response_text, error) tuple
        """
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, model=model, system=system,
                         temperature=temperature, max_tokens=max_tokens)


# Global singleton
_ollama_local = None

def get_ollama_client() -> OllamaLocalClient:
    """Get or create the global Ollama local client"""
    global _ollama_local
    if _ollama_local is None:
        _ollama_local = OllamaLocalClient()
    return _ollama_local


def is_ollama_available() -> bool:
    """Check if local Ollama is running and accessible"""
    client = get_ollama_client()
    return client._is_available()


if __name__ == "__main__":
    print("Testing Local Ollama Client...")

    client = get_ollama_client()
    print(f"\n1. Server available: {client._is_available()}")
    print(f"   Models: {client.list_models()}")

    if client._is_available():
        print(f"\n2. Testing chat with {client.default_model}:")
        response, error = client.chat(
            messages=[{"role": "user", "content": "Say hello in exactly 5 words."}],
            temperature=0.5,
            max_tokens=100,
        )
        if error:
            print(f"   Error: {error}")
        else:
            print(f"   Response: {response}")

        print(f"\n3. Testing system prompt:")
        response2, error2 = client.chat(
            messages=[{"role": "user", "content": "What is 2+2?"}],
            system="You are a math tutor. Answer briefly and only give the number.",
            temperature=0.3,
            max_tokens=50,
        )
        if error2:
            print(f"   Error: {error2}")
        else:
            print(f"   Response: {response2}")
