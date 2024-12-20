from openai import OpenAI
import os
from typing import List, Dict, Any

class AIAssistant:
    # 硬编码的API密钥
    DEFAULT_API_KEY = "sk-8bed45a8e6714f54af303d4c99e565bd"  # 请替换为你的实际API密钥
    
    def __init__(self, api_key: str = None):
        """
        初始化AI助手
        :param api_key: DeepSeek API密钥，如果不提供则使用环境变量或默认密钥
        """
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or self.DEFAULT_API_KEY
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )

    def get_response(self, user_message: str, system_message: str = "你是一个帮助用户清理磁盘的AI助手。") -> str:
        """
        获取AI助手的回复
        :param user_message: 用户消息
        :param system_message: 系统提示消息
        :return: AI助手的回复
        """
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                stream=False
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"抱歉，发生了错误：{str(e)}"

    def analyze_disk_usage(self, path_info: str) -> str:
        """
        分析磁盘使用情况并提供建议
        :param path_info: 包含路径使用情况的信息
        :return: AI分析和建议
        """
        prompt = f"""
请分析以下磁盘使用情况，并提供清理建议：
{path_info}

请提供：
1. 对当前磁盘使用状况的简要分析
2. 具体的清理建议
3. 需要注意的安全事项
"""
        return self.get_response(prompt)

# 使用示例
if __name__ == "__main__":
    # 使用默认API密钥创建助手实例
    assistant = AIAssistant()
    response = assistant.get_response("你好，请帮我分析一下我的磁盘使用情况。")
    print(response) 