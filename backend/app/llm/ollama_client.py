from app.core.config import settings


class OllamaClient:
    """Placeholder client for interacting with local Ollama LLM instance."""

    def __init__(self, base_url: str = settings.OLLAMA_BASE_URL, model: str = settings.OLLAMA_MODEL):
        self.base_url = base_url
        self.model = model

    def generate(self, prompt: str) -> str:
        # Placeholder LLM response
        return "Placeholder LLM response from Ollama"
