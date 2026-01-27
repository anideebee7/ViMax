import json
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from utils.core.retry import after_func

class PacingAnalysis(BaseModel):
    is_pacing_correct: bool = Field(..., description="True if the story beats occur at the correct timestamps")
    pacing_score: float = Field(..., description="Score from 0-10 on narrative flow")
    bottlenecks: List[str] = Field(default_factory=list, description="Sections where the story drags or feels rushed")
    required_shifts: List[str] = Field(default_factory=list, description="Specific instructions to move plot points")
    revised_outline_suggestion: Optional[str] = Field(None, description="A suggested fix for the chapter outline")

class StructureSupervisor:
    """Agent that ensures feature films follow a rigorous three-act structure and maintain perfect pacing."""
    
    def __init__(self, chat_model):
        self.chat_model = chat_model
        self.logger = logging.getLogger(self.__class__.__name__)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def analyze_pacing(
        self,
        outline: List[Dict[str, Any]],
        target_runtime_minutes: int,
        genre: str
    ) -> PacingAnalysis:
        """Analyzes a chapter outline against mathematical pacing standards for the genre."""
        
        parser = PydanticOutputParser(pydantic_object=PacingAnalysis)
        
        system_prompt = f"""
        [Role]
        You are a world-class "Structure Supervisor" and script consultant. You are an expert in the mathematical architecture of cinema. You ensure that films never "drag" and that every beat lands with maximum impact.
        
        [Task]
        Review the provided CHAPTER OUTLINE against the TARGET RUNTIME ({target_runtime_minutes} mins) and GENRE ({genre}).
        
        [Standards]
        - ACT 1 (Setup): Should end at ~25% of runtime. The "Point of No Return" must be clear.
        - MIDPOINT: A major reversal or stakes-escalation must happen at EXACTLY ~50% of runtime.
        - ACT 2 (Confrontation): Act 2 climaxes at ~75% of runtime.
        - ACT 3 (Resolution): Rapid escalation to the final climax and resolution.
        
        [Output]
        {parser.get_format_instructions()}
        """
        
        human_prompt = f"""
        <OUTLINE>
        {json.dumps(outline, indent=2)}
        </OUTLINE>
        
        <RUNTIME>
        {target_runtime_minutes} minutes
        </RUNTIME>
        
        Analyze the pacing. If the midpoint is missing or misplaced, or if Act 2 is too long without a major shift, flag it as a failure and provide specific instructions for a rewrite.
        """
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ]
        
        chain = self.chat_model | parser
        return await chain.ainvoke(messages)
