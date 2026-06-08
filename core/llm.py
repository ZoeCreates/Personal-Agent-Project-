from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

class LLMClient:
    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url=os.getenv("BASE_URL", "https://api.groq.com/openai/v1")
        )
        self.model = os.getenv("MODEL", "llama-3.3-70b-versatile")

    def chat(self, messages: list, tools: list = None):
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message
