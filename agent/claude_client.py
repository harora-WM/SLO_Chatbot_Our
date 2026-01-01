"""Claude Bedrock client for conversational AI."""

import json
import boto3
from typing import Dict, List, Any, Optional
from utils.logger import setup_logger
from utils.config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    BEDROCK_MODEL_ID
)

logger = setup_logger(__name__)


class ClaudeClient:
    """Client for AWS Bedrock Claude API."""

    def __init__(self):
        """Initialize Claude client."""
        self.bedrock = boto3.client(
            service_name='bedrock-runtime',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )
        self.model_id = BEDROCK_MODEL_ID
        self.conversation_history = []

        logger.info(f"Claude client initialized with model {self.model_id}")

    def send_message(self,
                    user_message: str,
                    tools: Optional[List[Dict[str, Any]]] = None,
                    system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Send a message to Claude and get response.

        Args:
            user_message: User's message
            tools: Optional list of tool definitions for function calling
            system_prompt: Optional system prompt

        Returns:
            Claude's response
        """
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Prepare request
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": self.conversation_history,
            "temperature": 0.7
        }

        if system_prompt:
            request_body["system"] = system_prompt

        if tools:
            request_body["tools"] = tools

        try:
            # Call Bedrock API
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )

            # Parse response
            response_body = json.loads(response['body'].read())

            # Add assistant response to history
            self.conversation_history.append({
                "role": "assistant",
                "content": response_body.get("content", [])
            })

            logger.info(f"Claude response received (stop_reason: {response_body.get('stop_reason')})")

            return response_body

        except Exception as e:
            logger.error(f"Failed to call Claude API: {e}")
            raise

    def handle_tool_use(self,
                       response: Dict[str, Any],
                       tool_executor: Any) -> Optional[Dict[str, Any]]:
        """Handle tool use from Claude's response.

        Args:
            response: Claude's response containing tool use
            tool_executor: Function executor instance

        Returns:
            Final response after tool execution, or None if no tool use
        """
        content = response.get("content", [])

        # Check if response contains tool use
        tool_uses = [block for block in content if block.get("type") == "tool_use"]

        if not tool_uses:
            return None

        # Execute each tool
        tool_results = []
        for tool_use in tool_uses:
            tool_name = tool_use.get("name")
            tool_input = tool_use.get("input", {})
            tool_use_id = tool_use.get("id")

            logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

            try:
                # Execute the tool
                result = tool_executor.execute(tool_name, tool_input)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps(result)
                })

                logger.info(f"Tool {tool_name} executed successfully")

            except Exception as e:
                logger.error(f"Tool execution failed: {e}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps({"error": str(e)})
                })

        # Send tool results back to Claude
        self.conversation_history.append({
            "role": "user",
            "content": tool_results
        })

        # Get final response
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": self.conversation_history,
            "temperature": 0.7
        }

        try:
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )

            response_body = json.loads(response['body'].read())

            # Add to history
            self.conversation_history.append({
                "role": "assistant",
                "content": response_body.get("content", [])
            })

            return response_body

        except Exception as e:
            logger.error(f"Failed to get final response: {e}")
            raise

    def chat(self,
            user_message: str,
            tools: Optional[List[Dict[str, Any]]] = None,
            tool_executor: Optional[Any] = None,
            system_prompt: Optional[str] = None) -> str:
        """Complete chat interaction with tool support.

        Args:
            user_message: User's message
            tools: Optional tool definitions
            tool_executor: Optional tool executor
            system_prompt: Optional system prompt

        Returns:
            Final text response from Claude
        """
        # Get initial response
        response = self.send_message(user_message, tools, system_prompt)

        # Handle tool use if present
        if tool_executor and response.get("stop_reason") == "tool_use":
            response = self.handle_tool_use(response, tool_executor)

        # Extract text response
        text_response = ""
        for block in response.get("content", []):
            if block.get("type") == "text":
                text_response += block.get("text", "")

        return text_response

    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []
        logger.info("Conversation history cleared")

    def get_history(self) -> List[Dict[str, Any]]:
        """Get conversation history.

        Returns:
            List of conversation messages
        """
        return self.conversation_history
