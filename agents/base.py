import json
import logging
from typing import Any, Type, TypeVar
from pydantic import BaseModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt
from utils.core.retry import after_func

T = TypeVar("T", bound=BaseModel)

class BaseAgent:
    """Base class for all agents with common utilities like JSON auto-repair."""
    
    def __init__(self, chat_model):
        self.chat_model = chat_model
        self.logger = logging.getLogger(self.__class__.__name__)

    async def _repair_json(self, malformed_json: str, schema: Type[T]) -> T:
        """Uses a fast model to repair malformed JSON string before parsing."""
        repair_prompt = f"""
        [Role]
        You are an elite JSON repair expert. You receive malformed JSON strings and fix them to be valid JSON according to a specific schema.
        
        [Task]
        Repair the following malformed JSON string. 
        - Ensure all quotes are correct.
        - Fix missing commas or brackets.
        - Ensure it matches the requested schema structure.
        - OUTPUT ONLY THE VALID JSON. NO EXPLANATIONS.
        
        [Schema]
        {schema.model_json_schema()}
        
        [Malformed JSON]
        {malformed_json}
        """
        
        self.logger.info("Attempting to repair malformed JSON...")
        messages = [
            SystemMessage(content="You are a JSON repair tool. Output only valid JSON."),
            HumanMessage(content=repair_prompt)
        ]
        
        # We assume self.chat_model is already initialized and capable
        response = await self.chat_model.ainvoke(messages)
        content = response.content.strip()
        
        # Clean up possible markdown code blocks
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        parser = PydanticOutputParser(pydantic_object=schema)
        return parser.parse(content)

    async def parse_with_repair(self, content: str, schema: Type[T]) -> T:
        """Tries to parse content, if fails, attempts to repair it."""
        parser = PydanticOutputParser(pydantic_object=schema)
        try:
            return parser.parse(content)
        except Exception as e:
            self.logger.warning(f"Initial parsing failed: {e}. Attempting auto-repair...")
            try:
                return await self._repair_json(content, schema)
            except Exception as repair_error:
                self.logger.error(f"Auto-repair failed: {repair_error}")
                raise repair_error
