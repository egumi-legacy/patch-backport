import tiktoken
from openai import OpenAI
from loguru import logger

class OpenAI_Client:
    __MODEL_LIMITS = {
        "gpt-3.5-turbo": 16_385,
        "gpt-4	": 8_192,
        "gpt-4-turbo": 8_192,
        "o1-mini": 128_000,
        "gpt-4o-mini": 128_000,
        "gpt-4o": 128_000,
    }
    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
        )

    def __is_url_valid(self, url):
        if self.base_url is None or self.base_url != "https://api.openai-proxy.org/v1":
            return False
        return True

    def __get_model_limit(self, model):
        return self.__MODEL_LIMITS.get(model, 128_000)

    def check_prompt_length(self, messages, model):
        model_limit = self.__get_model_limit(model)
        encoding = tiktoken.encoding_for_model(model)
        token_count = 0
        for message in messages:
            token_count += len(encoding.encode(message["content"]))
            if token_count > model_limit:
                return -1
        return model_limit - token_count

    # TO: truncate_messages
    # def truncate_messages(self, messages, model):