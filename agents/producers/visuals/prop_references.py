import os
import logging
from typing import List, Dict, Optional
from interfaces.entities.prop import PropInScene
from utils.core.retry import after_func
from tenacity import retry, stop_after_attempt

class PropReferenceGenerator:
    """Agent that generates consistent visual reference images for critical props/objects."""
    
    def __init__(self, image_generator):
        self.image_generator = image_generator
        self.logger = logging.getLogger(self.__class__.__name__)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def generate_prop_reference(
        self,
        prop: PropInScene,
        style: str,
        output_dir: str,
        force_regenerate: bool = False
    ) -> str:
        """Generates a high-quality reference image for a prop."""
        
        save_path = os.path.join(output_dir, f"prop_{prop.identifier.lower().replace(' ', '_')}.png")
        
        # Check if prop reference already exists
        if os.path.exists(save_path) and not force_regenerate:
            self.logger.info(f"Prop reference already exists for {prop.identifier}, skipping generation.")
            return save_path
        
        prompt = f"""
        [Prop Reference]
        Object: {prop.identifier}
        Description: {prop.description}
        Static Features: {prop.static_features}
        Visual Style: {style}
        
        [Task]
        Generate a studio-quality product shot of this object against a neutral, solid gray background. 
        Focus on extreme detail, material texture, and iconic silhouette. 
        The object should be the ONLY thing in the frame.
        """
        
        self.logger.info(f"Generating visual reference for prop: {prop.identifier}")
        
        image_output = await self.image_generator.generate_single_image(
            prompt=prompt,
            size="1024x1024"
        )
        
        os.makedirs(output_dir, exist_ok=True)
        image_output.save(save_path)
        return save_path
