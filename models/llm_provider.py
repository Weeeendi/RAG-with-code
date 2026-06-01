from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class BaseLLM(ABC):
    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        pass

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        pass


class MiniMaxLLM(BaseLLM):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.minimax.chat/v1",
        model: str = "MiniMax-M2.7",
        max_tokens: int = 800,
        temperature: float = 0.3
    ):
        import requests
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._requests = requests

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": kwargs.get("model", self.model),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "messages": messages
        }
        response = self._requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=kwargs.get("timeout", 30)
        )
        if response.status_code == 200:
            result = response.json()
            if result.get("choices") and result["choices"][0].get("message", {}).get("content"):
                return result["choices"][0]["message"]["content"]
        raise Exception(f"API error: {response.status_code} - {response.text}")

    def generate(self, prompt: str, **kwargs) -> str:
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, **kwargs)


class SiliconFlowLLM(BaseLLM):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.siliconflow.cn/v1",
        model: str = "Qwen/Qwen2.5-7B-Instruct",
        max_tokens: int = 800,
        temperature: float = 0.3
    ):
        import requests
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._requests = requests

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": kwargs.get("model", self.model),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "messages": messages
        }
        response = self._requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=kwargs.get("timeout", 30)
        )
        if response.status_code == 200:
            result = response.json()
            if result.get("choices") and result["choices"][0].get("message", {}).get("content"):
                return result["choices"][0]["message"]["content"]
        raise Exception(f"API error: {response.status_code} - {response.text}")

    def generate(self, prompt: str, **kwargs) -> str:
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, **kwargs)


class OpenAICompatibleLLM(BaseLLM):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 800,
        temperature: float = 0.3
    ):
        import requests
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._requests = requests

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": kwargs.get("model", self.model),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "messages": messages
        }
        response = self._requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=kwargs.get("timeout", 30)
        )
        if response.status_code == 200:
            result = response.json()
            if result.get("choices") and result["choices"][0].get("message", {}).get("content"):
                return result["choices"][0]["message"]["content"]
        raise Exception(f"API error: {response.status_code} - {response.text}")

    def generate(self, prompt: str, **kwargs) -> str:
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, **kwargs)
