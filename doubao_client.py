import os
from openai import OpenAI
from loguru import logger
from pathlib import Path
import requests

class Doubao_Client:
    __MODEL_LIMITS = {
        # 示例模型ID及其token限制，实际可根据官方文档补充
        "doubao-seed-1.6": 256_000,
        "doubao-seed-1.6-flash": 256_000,
        "deepseek-r1": 96_000,
    }
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or os.environ.get("ARK_API_KEY")
        # print("="*100)
        # print(f"api_key: {self.api_key}")
        # print("="*100)
        self.base_url = base_url or "https://ark.cn-beijing.volces.com/api/v3"
        if self.base_url.endswith("/"):
            self.base_url = self.base_url[:-1]
        self.tokenization_url = f"{self.base_url}/tokenization"
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )

    def __get_model_limit(self, model):
        return self.__MODEL_LIMITS.get(model, 128_000)

    def get_token_count(self, model, texts):
        """
        调用豆包分词API获取token数，texts为字符串或字符串列表，返回每条文本的token数列表
        """
        if isinstance(texts, str):
            texts = [texts]
        url = self.tokenization_url
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": model,
            "text": texts
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            token_counts = [item["total_tokens"] for item in data.get("data", [])]
            return token_counts
        except Exception as e:
            logger.error(f"豆包分词API调用失败: {e}")
            # 失败时回退为字符数估算
            return [len(t) for t in texts]

    def check_prompt_length(self, prompts, model):
        model_limit = self.__get_model_limit(model)
        texts = [prompt["content"] for prompt in prompts]
        token_counts = self.get_token_count(model, texts)
        token_count = sum(token_counts)
        if token_count > model_limit:
            return -1
        return model_limit - token_count

    # TO: truncate_messages
    # def truncate_messages(self, messages, model):

    def call_openai(self, model, messages, thinking_type="enabled"):
        """
        thinking_type: 可选，'enabled' 或 'disabled'，控制豆包深度思考能力
        """
        extra_body = None
        if thinking_type in ("enabled", "disabled"):
            extra_body = {"thinking": {"type": thinking_type}}
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            extra_body=extra_body
        ) 