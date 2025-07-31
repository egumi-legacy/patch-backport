from openai import OpenAI
from loguru import logger
import os

class Deepseek_Client:
    __MODEL_LIMITS = {
        "deepseek-chat": 64_000,
        "deepseek-reasoner": 64_000,
    }

    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.base_url = base_url or "https://api.deepseek.com/v1"
        if self.base_url.endswith("/"):
            self.base_url = self.base_url[:-1]
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )

    def __get_model_limit(self, model):
        return self.__MODEL_LIMITS.get(model, 128_000)

    def check_prompt_length(self, prompts, model):
        model_limit = self.__get_model_limit(model)
        token_count = 0
        for prompt in prompts:
            content = prompt["content"]
            # 这里没有官方tokenizer，简单用字符数估算
            token_count += len(content)
            if token_count > model_limit:
                return -1
        return model_limit - token_count

    # TO: truncate_messages
    # def truncate_messages(self, messages, model):

    def call_openai(self, model, messages):
        return self.client.chat.completions.create(model=model, messages=messages, stream=True) 