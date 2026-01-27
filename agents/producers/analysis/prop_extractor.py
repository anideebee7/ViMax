import logging
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from typing import List, Literal
from tenacity import retry, stop_after_attempt
from agents.base import BaseAgent
from interfaces.entities.prop import PropInScene
from utils.core.retry import after_func

SYSTEM_PROMPT = """
[Role]
You are a meticulous movie production designer and script analyst. You excel at identifying key props and environment visual anchors that are essential for narrative continuity.

[Task]
Analyze the provided script and extract:
1. KEY PROPS: Significant objects that characters interact with or that are central to the story (e.g., 'A vintage compass', 'A glowing blue orb', 'A blood-stained letter').
2. VISUAL ANCHORS: Persistent background elements that define the location's visual identity (e.g., 'A flickering neon sign', 'A massive mahogany desk', 'A cracked stained-glass window').

[Output]
{format_instructions}

[Guidelines]
- PROPS: Only extract objects that have narrative weight. Ignore generic items like "a chair" unless it's a specific, unique chair.
- VISUAL ANCHORS: These are not props (movable objects) but fixed parts of the environment that help the audience recognize the location across different shots.
- DESCRIPTIONS: Must be vivid, detailed, and visually specific. Avoid abstract terms. Describe materials, colors, textures, and signs of wear.
- CONSISTENCY: Ensure that the description of a prop/anchor remains stable throughout the script.
"""

HUMAN_PROMPT = """
<SCRIPT>
{script}
</SCRIPT>

Identify all critical props and visual anchors for this production.
"""

class PropExtractionResponse(BaseModel):
    props: List[PropInScene] = Field(..., description="List of key narrative props")
    visual_anchors: List[str] = Field(..., description="List of background visual anchors")

class PropExtractor(BaseAgent):
    def __init__(self, chat_model):
        super().__init__(chat_model)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def extract_props_and_anchors(self, script: str) -> PropExtractionResponse:
        parser = PydanticOutputParser(pydantic_object=PropExtractionResponse)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(content=HUMAN_PROMPT.format(script=script))
        ]
        
        response = await self.chat_model.ainvoke(messages)
        return await self.parse_with_repair(response.content, PropExtractionResponse)
