from openai import OpenAI
from loguru import logger
from pathlib import Path
from dashscope import get_tokenizer

class QWen_Client:
    __MODEL_LIMITS = {
        "qwen-max": 32_768,
        "qwen-plus-latest": 129_024,
        "qwen-plus": 131_072,
        "qwen-turbo": 131_072,
        "qwen-long": 10_000_000
    }
    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
        )


    def __get_model_limit(self, model):
        return self.__MODEL_LIMITS.get(model, 128_000)

    def check_prompt_length(self, prompts, model):
        model_limit = self.__get_model_limit(model)
        print(f"model: {model}")
        tokenizer = get_tokenizer(model)
        token_count = 0
        for prompt in prompts:
            content = prompt["content"]
            token_count += len(tokenizer.encode(content))
            if token_count > model_limit:
                return -1
        return model_limit - token_count

    # TO: truncate_messages
    # def truncate_messages(self, messages, model):

    def call_openai(self, model, messages):
        return self.client.chat.completions.create(model=model, messages=messages, stream=True)