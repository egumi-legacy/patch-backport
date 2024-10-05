import os
import json
from openai import OpenAI

class LLMAssistant:
    def __init__(self, inputs):
        # 默认从环境变量中获取API密钥和基础URL
        inputs.setdefault("openai_api_key", os.getenv("OPENAI_API_KEY"))
        inputs.setdefault("openai_base_url", os.getenv("OPENAI_BASE_URL"))

        _api_key = inputs.get("openai_api_key")
        _base_url = inputs.get("openai_base_url")

        if not _api_key or not _base_url:
            raise ValueError("请确保输入中包含api_key, base_url, 或者设置了OPENAI_API_KEY和OPENAI_BASE_URL环境变量")

        self.client = OpenAI_Client(_api_key, _base_url)
        self.model = inputs.get("model", "gpt-4o")
        self.save_response_to_file = inputs.get("save_response_to_file", None)

        prompt_file = inputs.get("prompt_file")
        if prompt_file is not None:
            prompt_file_path = Path(prompt_file)
            if not prompt_file_path.is_file():
                raise ValueError(f'Unable to find Prompt file: "{prompt_file}"')
            try:
                with open(prompt_file_path, "r") as fp:
                    self.prompts = json.load(fp)
            except json.JSONDecodeError as e:
                raise ValueError(f'Invalid Json Prompt file "{prompt_file}": {e}')
        elif "prompts" in inputs.keys():
            self.prompts = inputs["prompts"]
        else:
            raise ValueError('Missing required data: "prompt_file" or "prompts"')


    def save_response_to_file(self, responses):
        file_path = os.path.abspath(self.save_response_to_file)
        mode = "a" if os.path.exists(file_path) else "w"
        with open(file_path, mode) as f:
            for prompt, response in zip(self.prompts, responses):
                data = {
                    "model": self.model,
                    "prompt": prompt,
                    "response": response,
                }
                json.dump(data, f, indent=4)
                f.write("\n")

    def analyze_patch(self, patch_content):
        # 使用LLM分析patch
        pass

    def call_llm(self, prompts):
        response = []
        for prompt in prompts:
            is_valid = self.client.check_prompt_length(prompt, self.model) > 0
            if not is_valid:
                # TODO: 使用truncate_messages   
                logger.error(f"Prompt is too long")
                continue
            logger.trace(f"Message sent: \n{escape(indent(pformat(prompt), '  '))}")
            try:
                completion = self.client.chat.completions.create(model=self.model, messages=prompt, )
            except Exception as e:
                logger.error(f"Error calling OpenAI: {e}")
                completion = None
                continue
            
            response.append(completion)
        return response

    def suggest_adaptation(self, patch_content, target_version):
        # 使用LLM提供适配建议
        pass

    def resolve_conflict(self, conflict_info):
        # 使用LLM解决冲突
        pass