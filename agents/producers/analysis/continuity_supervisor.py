import json
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from utils.core.retry import after_func

class ConsistencyIssue(BaseModel):
    issue_type: str = Field(..., description="Type: 'character_drift', 'background_jump', 'prop_mismatch', 'voice_shift'")
    severity: str = Field(..., description="'critical', 'high', 'medium', 'low'")
    timestamp_range: str = Field(..., description="e.g., '0:45 - 0:52'")
    description: str = Field(..., description="What specifically went wrong")
    fix_suggestion: str = Field(..., description="How to fix it (e.g., 'Regenerate shot 12 with Image 11 background')")

class ContinuityReport(BaseModel):
    overall_score: float = Field(..., description="0-10 score on temporal consistency")
    issues: List[ConsistencyIssue] = Field(default_factory=list)
    is_production_ready: bool = Field(..., description="True if no critical/high issues remain")

class TemporalConsistencyAgent:
    """Agent that reviews final video output for temporal jumps and continuity errors."""
    
    def __init__(self, chat_model):
        self.chat_model = chat_model
        self.logger = logging.getLogger(self.__class__.__name__)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def review_continuity(
        self,
        script: str,
        storyboard: List[Dict[str, Any]],
        video_metadata: Dict[str, Any]
    ) -> ContinuityReport:
        """Reviews the production metadata and script to identify logic/visual gaps."""
        
        parser = PydanticOutputParser(pydantic_object=ContinuityReport)
        
        system_prompt = f"""
        [Role]
        You are an elite "Continuity Supervisor" (Script Supervisor) for a major film studio. Your job is to catch every single mistake—from a character's shirt color changing between cuts to a background object disappearing.
        
        [Task]
        Analyze the provided SCRIPT and STORYBOARD for logical and visual continuity gaps.
        
        [Checklist]
        1. CHARACTER DRIFT: Does a character's appearance change without reason?
        2. BACKGROUND LOCK: Is the set identical across shots in the same location?
        3. PROP PERSISTENCE: If a character picks up an object, do they still have it in the next shot?
        4. SPATIAL LOGIC: Do camera angles respect the 180-degree rule and set geography?
        
        [Output]
        {parser.get_format_instructions()}
        """
        
        human_prompt = f"""
        <SCRIPT>
        {script[:5000]}
        </SCRIPT>
        
        <STORYBOARD>
        {json.dumps(storyboard, indent=2)}
        </STORYBOARD>
        
        Identify any continuity issues that would break immersion for the viewer.
        """
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ]
        
        chain = self.chat_model | parser
        return await chain.ainvoke(messages)

class ContinuitySupervisor(TemporalConsistencyAgent):
    """Alias for TemporalConsistencyAgent for backward compatibility."""
    pass
