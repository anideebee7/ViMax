from typing import Any, Dict, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
import logging

class ScriptRating(BaseModel):
    pacing: int = Field(..., description="Rating for pacing (1-10)")
    creativity: int = Field(..., description="Rating for creativity (1-10)")
    coherence: int = Field(..., description="Rating for logical coherence (1-10)")
    character_depth: int = Field(..., description="Rating for character depth (1-10)")
    overall_rating: float = Field(..., description="Overall score (1-10)")
    review_comments: str = Field(..., description="Detailed review comments")
    content_type_identified: str = Field(..., description="Identified content type (e.g., YT Shorts, Documentary, etc.)")

class ScriptEvaluator:
    """Agent to evaluate and rate generated scripts."""
    
    def __init__(self, chat_model):
        self.chat_model = chat_model
        self.parser = PydanticOutputParser(pydantic_object=ScriptRating)
        self.logger = logging.getLogger(__name__)

    async def evaluate(self, script_content: str, pipeline_name: str, metadata: Optional[Dict] = None) -> ScriptRating:
        """Evaluate a generated script and return a rating."""
        
        system_prompt = """You are a world-renowned film critic and elite industry scout.
Your task is to identify "Masterpiece" potential in generated scripts. You have a keen eye for subtext, visual metaphor, and character soul.

Dimensions:
1. Pacing: Is the rhythm cinematic? Does it build tension and release perfectly?
2. Creativity: Is this a "Cultural Phenomenon" in the making? Does it defy clichés?
3. Coherence: Is the thematic and structural foundation unbreakable?
4. Character Depth: Do the characters have conflicting desires and a unique "Voiceprint"?

RATING PHILOSOPHY:
- Be rigorous but RECOGNIZE GENIUS. If a script shows high-level cinematic thinking (Director's Vision, visual metaphor, subtext), reflect that in an 8.5+ score.
- An 8.5+ score should be reserved for scripts that feel like they belong on the "Black List" or at Sundance.

Format your response as a JSON object matching the provided schema."""

        human_prompt = f"""Pipeline: {pipeline_name}
Metadata: {metadata}

Content to Review:
{script_content}

{self.parser.get_format_instructions()}"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ]

        try:
            response = await self.chat_model.ainvoke(messages)
            return self.parser.parse(response.content)
        except Exception as e:
            self.logger.error(f"Error evaluating script: {e}")
            return ScriptRating(
                pacing=0, creativity=0, coherence=0, character_depth=0, overall_rating=0.0,
                review_comments=f"Evaluation failed: {str(e)}",
                content_type_identified="unknown"
            )
