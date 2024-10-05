import os
from openai import OpenAI
import tiktoken

# # 从环境变量中获取API密钥和基础URL
# api_key = os.getenv('OPENAI_API_KEY')
# base_url = os.getenv('OPENAI_BASE_URL')

# # 确保环境变量已设置
# if not api_key or not base_url:
#     raise ValueError("请确保设置了OPENAI_API_KEY和OPENAI_BASE_URL环境变量")

# # 使用环境变量创建客户端
# client = OpenAI(
#     base_url=base_url,
#     api_key=api_key,
# )

def test_openai_api(prompt):
    try:
        # 创建一个聊天完成请求
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "你是一个友好的AI助手，专门回答关于人工智能的问题。",
                },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="gpt-3.5-turbo",
        )

        # 打印响应
        print("API响应:")
        print(chat_completion.choices[0].message.content)

    except Exception as e:
        print(f"发生错误: {str(e)}")

# 运行测试
if __name__ == "__main__":
    # user_prompt = input("请输入您的问题：")
    # test_openai_api(user_prompt)
    # 创建编码器
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")

    # 编码文本
    tokens = encoding.encode("Hello, world!")

    # 解码 tokens
    text = encoding.decode(tokens)

    print(f"Tokens: {tokens}")
    print(f"Decoded text: {text}")
