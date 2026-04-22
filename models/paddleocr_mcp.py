import os
import json
import subprocess
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import sys
sys.path.insert(0, r'D:\workspace\Agent')
from config import PADDLEOCR_TOKEN


def _get_mcp_server_config() -> dict:
    return {
        "command": "uvx",
        "args": ["--from", "paddleocr-mcp", "paddleocr_mcp"],
        "env": {
            "PADDLEOCR_MCP_PIPELINE": "PaddleOCR-VL",
            "PADDLEOCR_MCP_PPOCR_SOURCE": "aistudio",
            "PADDLEOCR_MCP_SERVER_URL": "https://tc1243l70es0i4pd.aistudio-app.com",
            "PADDLEOCR_MCP_AISTUDIO_ACCESS_TOKEN": PADDLEOCR_TOKEN
        }
    }


MCP_SERVER_CONFIG = _get_mcp_server_config()


@dataclass
class MCPToolResult:
    success: bool
    data: Any = None
    error: Optional[str] = None


class PaddleOCRMCPClient:
    def __init__(self, config: dict = None):
        self.config = config or MCP_SERVER_CONFIG
        self.process: subprocess.Popen = None
        self._start_server()

    def _start_server(self):
        env = os.environ.copy()
        env.update(self.config.get("env", {}))

        cmd = [self.config["command"]] + self.config["args"]
        self.process = subprocess.Popen(
            cmd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

    def _send_request(self, method: str, params: dict = None) -> dict:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {}
        }
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()

        response_line = self.process.stdout.readline()
        if response_line:
            return json.loads(response_line)
        return {"error": {"code": -1, "message": "No response"}}

    def call_tool(self, tool_name: str, arguments: dict) -> MCPToolResult:
        response = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

        if "result" in response:
            return MCPToolResult(success=True, data=response["result"])
        elif "error" in response:
            return MCPToolResult(success=False, error=str(response["error"]))
        return MCPToolResult(success=False, error="Unknown error")

    def parse_document(self, file_path: str) -> MCPToolResult:
        return self.call_tool("parse_document", {
            "file_path": file_path
        })

    def close(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


def get_paddleocr_mcp_tools() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "paddleocr_mcp",
                "description": "使用PaddleOCR解析PDF文档，提取文本和表格。适用于扫描版PDF、截图等无法直接提取文本的文档。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "PDF文件的绝对路径"
                        }
                    },
                    "required": ["file_path"]
                }
            }
        }
    ]


def execute_paddleocr_mcp(file_path: str) -> MCPToolResult:
    client = PaddleOCRMCPClient()
    try:
        return client.parse_document(file_path)
    finally:
        client.close()
