import os
import json
from qwen_client import QWen_Client
from loguru import logger
import dotenv
from pathlib import Path
import pprint
from textwrap import indent
from pprint import pformat
from chevron import render
import html
from config_manager import ProjectConfig

class LLMAssistant:
    def __init__(self, config: ProjectConfig):
        """
        初始化LLM助手
        
        :param config: 项目配置对象
        """
        dotenv.load_dotenv()
        self.config = config
        
        # 从环境变量获取API密钥和基础URL
        _api_key = os.environ.get("OPENAI_API_KEY")
        _base_url = os.environ.get("OPENAI_BASE_URL")

        if not _api_key or not _base_url:
            raise ValueError("请确保设置了环境变量 OPENAI_API_KEY 和 OPENAI_BASE_URL")

        # 初始化API客户端
        self.client = QWen_Client(_api_key, _base_url)
        
        # 从配置获取其他非敏感信息
        self.model = config.model
        self.response_file = config.response_file
        self.prompt_template_file = config.prompt_template_file
        self.prompt_id = config.prompt_id
        print(f"config in LLM:{config}")
        
        self.prompt_values = config.extra_config.get("prompt_values")
        print(f"self.prompt_values:{self.prompt_values}")
        self.prompt_value_file = config.prompt_value_file
        # self.prompts = self.preprocess_prompts().get("prompts")
        self._prompts = None
        self.partitions = config.extra_config.get("partitions", [])
        self.use_cache = config.use_cache
        self.cache_path = config.extra_config.get("cache_path")
        # self.cache_path = config.base_dir / 

    @property
    def prompts(self):
        """延迟加载prompts"""
        if self._prompts is None:
            processed = self.preprocess_prompts()
            self._prompts = processed.get("prompts")
        return self._prompts

    def get_prompt_template_from_file(self, prompt_template_file, prompt_id):
        """从文件中获取prompt模板"""
        if prompt_template_file is not None:
            prompt_template_file = Path(prompt_template_file)
            if not prompt_template_file.is_file():
                raise ValueError(f'Unable to find Prompt template file: "{prompt_template_file}"')
            try:
                with open(prompt_template_file, "r") as fp:
                    prompt_template = json.load(fp)
            except Exception as e:
                raise ValueError(f'Unable to read Prompt template file: "{prompt_template_file}": {e}')
        else:
            return None
            
        # 从文件中找到prompt_id对应的prompt
        found_prompt = None
        for prompt in prompt_template:
            if prompt["id"] == prompt_id:
                found_prompt = prompt

        prompts = found_prompt["prompts"]
        if prompts is None:
            logger.warning(f"key 'prompts' not found in prompt template file: {prompt_template_file}")
        
        return prompts

    def check_prompt_values(self):
        # 优先使用prompt_values，如果为空则使用prompt_value_file
        prompt_value_file = self.prompt_value_file
        prompt_values = self.prompt_values
        if prompt_value_file is None and prompt_values is None:
            raise ValueError(f"prompt_value_file and prompt_values are None")
        if prompt_values is None and not Path(prompt_value_file).is_file():
            raise ValueError(f"Unable to find Prompt value file: {prompt_value_file}")
        
        if prompt_values is None:
            try:
                with open(Path(prompt_value_file), "r") as fp:
                    prompt_values = json.load(fp)
            except Exception as e:
                raise ValueError(f"Unable to read Prompt value file: {prompt_value_file}: {e}")
        return prompt_values

    def save_response_to_file(self, responses):
        file_path = os.path.abspath(self.response_file)
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

    def preprocess_prompts(self):
        try:
            if len(self.prompt_values) == 0:
                logger.error(f"prompt_values is empty")
                return dict(prompts=[])
        except:
            raise Exception("there is an error.")

        # 从文件中找到prompt_id对应的prompt，即prompt_template中prompts字段下的字典列表
        self.prompt_template = self.get_prompt_template_from_file(self.prompt_template_file, self.prompt_id)
        if self.prompt_template is None:
            raise ValueError(f"{self.prompt_template_file} with id '{self.prompt_id}' is None")

        self.prompt_values = self.check_prompt_values()

        prompts = []
        for prompt_value in self.prompt_values:
            dict_value = prompt_value
            if not isinstance(dict_value, dict):
                dict_value = prompt_value.__dict__

            prompt = []
            for prompt_part in self.prompt_template:
                prompt_instance = {}
                for key, value in prompt_part.items():
                    print(f"key: {key}, value: {value}")
                    new_value = render(
                        template = value,
                        data = dict_value,
                    )
                    # 解码HTML转义字符
                    new_value = html.unescape(new_value)
                    print(f"new_value: {new_value}")
                    prompt_instance[key] = new_value
                prompt.append(prompt_instance)
            prompts.append(prompt)

        return dict(prompts=prompts)

    def call_llm(self, prompts):
        responses = []
        for prompt in prompts:
            # print(f"prompt in call_llm: {prompt}")
            # print(f"prompt[content]: {prompt['content']}")
            is_valid = self.client.check_prompt_length(prompt, self.model) > 0
            if not is_valid:
                # TODO: 使用truncate_messages   
                logger.error(f"Input is too long")
            logger.trace(f"Message sent: \n{indent(pformat(prompt), '  ')}")
            try:
                # completion = self.client.chat.completions.create(model=self.model, messages=prompts)
                completion = self.client.call_openai(self.model, prompt)
            except Exception as e:
                logger.error(f"Error calling OpenAI: {e}")
                completion = None
            
            # if completion is None or len(completion.choices) == 0:
            if completion is None:
                logger.error(f"No response from OpenAI")
                content = ""
                request_token = 0
                response_token = 0
            else:
                # 处理流式响应
                full_content = ""
                for chunk in completion:
                    if hasattr(chunk, 'choices') and len(chunk.choices) > 0:
                        if hasattr(chunk.choices[0], 'delta') and hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content is not None:
                            full_content += chunk.choices[0].delta.content
                content = full_content
                # request_token = completion.usage.prompt_tokens
                # response_token = completion.usage.completion_tokens
                request_token = 0  # Stream mode doesn't provide token counts
                response_token = 0

            logger.trace(f"Response received: \n{indent(content, '  ')}")

            responses.append({
                "prompt": prompt,
                "response": content,
                "request_token": request_token,
                "response_token": response_token,
            })
        return responses

    def extract_mode_response(self, openai_responses):
        if len(openai_responses) == 0:
            logger.error(f"openai_responses is empty")
            return dict(extracted_responses=[])

        outputs = []

        if len(self.partitions) == 0:
            logger.warning(f"partitions is empty. return openai_responses by defaultdict.")
            for openai_response in openai_responses:
                outputs.append(defaultdict(lambda: openai_response))
            return dict(extracted_responses=outputs)
        
        for openai_response in openai_responses:
            output = {}
            for key, partition in self.partitions.items():
                if len(partition) < 1:
                    output[key] = openai_response
                    continue
                
                extracted_response = openai_response
                for part in partition[:-1]:
                    _, _, extracted_response = extracted_response.partition(part)

                if partition[-1] == "":
                    extracted_response, _, _ = extracted_response.partition(partition[-1])

                if extracted_response == "":
                    continue
                
                output[key] = extracted_response
            outputs.append(output)
        
        return dict(extracted_responses=outputs)
                


    def suggest_adaptation(self, patch_content, target_version):
        # 使用LLM提供适配建议
        pass

    def analyze_patch(self, patch_content):
        # 使用LLM分析patch
        pass

    def resolve_conflict(self, conflict_info):
        # 使用LLM解决冲突
        pass

    def get_cached_response(self):
        """从缓存文件中读取响应"""
        if not self.cache_path:
            raise ValueError("未设置缓存路径，请检查配置")
            
        cache_path = Path(self.cache_path)
        if not cache_path.exists():
            raise ValueError(f"缓存文件不存在: {cache_path}")
            
        try:
            with open(cache_path, 'r') as f:
                response = f.read()
            logger.info(f"成功读取缓存响应: {cache_path}")
            return [response]  # 保持与 openai_responses 格式一致
        except Exception as e:
            logger.error(f"读取缓存响应失败: {e}")
            return None


    def run(self):
        if self.use_cache:
            cached_responses = self.get_cached_response()
            if cached_responses:
                logger.info("使用缓存的响应")
                return dict(
                    openai_responses=cached_responses,
                    request_tokens=[0],
                    response_tokens=[0]
                )
        prompts = self.prompts
        # print(f"prompts in run: {prompts}")
        responses = self.call_llm(prompts)

        openai_responses = []
        request_tokens = []
        response_tokens = []

        for response in responses:
            openai_responses.append(response["response"])
            request_tokens.append(response["request_token"])
            response_tokens.append(response["response_token"])

        print(f"openai_responses: {openai_responses}")
        print(f"request_tokens: {request_tokens}")
        print(f"response_tokens: {response_tokens}")

        if self.response_file:
            self.save_response_to_file(openai_responses)
        
        return dict(
            openai_responses=openai_responses,
            request_tokens=request_tokens,
            response_tokens=response_tokens,
        )
        
