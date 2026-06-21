# -*- coding: utf-8 -*-
# pip install openai
import os

from openai import OpenAI

api_key = os.getenv("AISTUDIO_API_KEY")
if not api_key:
    raise SystemExit("请先设置 AISTUDIO_API_KEY 环境变量后再运行该脚本。")

client = OpenAI(
    api_key=api_key,
    base_url="https://aistudio.baidu.com/llm/lmapi/v3",  # aistudio 大模型 api 服务域名
)

chat_completion = client.chat.completions.create(
    model="ernie-4.5-turbo-vl",
    messages=[
    {
        "role": "user",
        "content": "你好"
    },
    {
        "role": "assistant",
        "content": "你好！我是文心一言，很高兴为你服务。有什么我可以帮你的吗？无论是知识问答、文本创作、知识推理，还是日常聊天、分享笑话、讲故事，我都可以陪你一起探索。你今天想聊些什么呢？"
    },
    {
        "role": "user",
        "content": "在这里输入你的问题"
    }
],
    stream=True,
    extra_body={
        "web_search": {
            "enable": True
        }
    },
    max_completion_tokens=65536
)

for chunk in chat_completion:
    if not chunk.choices or len(chunk.choices) == 0:
        continue
    if hasattr(chunk.choices[0].delta, "reasoning_content") and chunk.choices[0].delta.reasoning_content:
        print(chunk.choices[0].delta.reasoning_content, end="", flush=True)
    else:
        print(chunk.choices[0].delta.content, end="", flush=True)
