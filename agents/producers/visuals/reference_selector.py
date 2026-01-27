import logging
import os
from typing import List, Tuple, Optional
from tenacity import retry, stop_after_attempt
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain.chat_models import init_chat_model
from utils.media.image import image_path_to_b64

from utils.core.retry import after_func

system_prompt_template_select_reference_images_only_text = \
"""
[Role]
You are a professional visual creation assistant skilled in multimodal image analysis and reasoning.

[Task]
Your core task is to intelligently select the most suitable reference images from a provided set of reference image descriptions (including multiple character reference images and existing scene images from prior frames) based on the user's text description (describing the target frame), ensuring that the subsequently generated image meets the following key consistencies:
- Character Consistency: The appearance (e.g. gender, ethnicity, age, facial features, hairstyle, body shape), clothing, expression, posture, etc., of the generated character should highly match the reference image descriptions.
- Environmental Consistency: The scene of the generated image (e.g., background, lighting, atmosphere, layout) should remain coherent with the existing image descriptions from prior frames.
- Style Consistency: The visual style of the generated image (e.g., realistic, cartoon, film-like, color tone) should harmonize with the reference image descriptions.

[Input]
You will receive a text description of the target frame, along with a sequence of reference image descriptions.
- The text description of the target frame is enclosed within <FRAME_DESC> and </FRAME_DESC>.
- The sequence of reference image descriptions is enclosed within <SEQ_DESC> and </SEQ_DESC>. Each description is prefixed with its index, starting from 0.

Below is an example of the input format:
<FRAME_DESC>
[Camera 1] Shot from Alice's over-the-shoulder perspective. Alice is on the side closer to the camera, with only her shoulder appearing in the lower left corner of the frame. Bob is on the side farther from the camera, positioned slightly right of center in the frame. Bob's expression shifts from surprise to delight as he recognizes Alice.
</FRAME_DESC>

<SEQ_DESC>
Image 0: A front-view portrait of Alice.
Image 1: A front-view portrait of Bob.
Image 2: [Camera 0] Medium shot of the supermarket aisle. Alice and Bob are shown in profile facing the right side of the frame. Bob is on the right side of the frame, and Alice is on the left side. Alice, looking down and pushing a shopping cart, follows closely behind Bob and accidentally bumps into his heel.
Image 3: [Camera 1] Shot from Alice's over-the-shoulder perspective. Alice is on the side closer to the camera, with only her shoulder appearing in the lower left corner of the frame. Bob is on the side farther from the camera, positioned slightly right of center in the frame. Bob quickly turns around, and his expression shifts from neutral to surprised.
Image 4: [Camera 2] Shot from Bob's over-the-shoulder perspective. Bob is on the side closer to the camera, with only his shoulder appearing in the lower right corner of the frame. Alice is on the side farther from the camera, positioned slightly left of center in the frame. Alice looks down, then up as she prepares to apologize. Upon realizing it's someone familiar, her expression shifts to one of surprise.
</SEQ_DESC>


[Output]
You need to select up to 8 of the most relevant reference images based on the user's description and put the corresponding indices in the ref_image_indices field of the output. At the same time, you should generate a text prompt that describes the image to be created, specifying which elements in the generated image should reference which image description (and which elements within it).

{format_instructions}


[Guidelines]
- Ensure that the language of all output values (not include keys) matches that used in the frame description.
- Character Consistency: Highly match character appearance and clothing from reference images.
- Prop Consistency: Identify and maintain key props (objects) from reference descriptions.
- Environmental Consistency: Use visual anchors and prior frame backgrounds to maintain location continuity.
- Style Consistency: Harmonize visual style with references.
- Prioritize image descriptions with similar compositions, i.e., shots taken by the same camera.
- Give higher priority to more recent images from prior frames.
- Choose reference image descriptions that are concise and avoid duplication.
- For character portraits, select at most one view (front, side, back).
- Select at most **8** optimal reference image descriptions.
- Identify the most stable "Visual Anchor" in the scene and ensure it is referenced in the prompt.
"""


system_prompt_template_select_reference_images_multimodal = \
"""
[Role]
You are a professional visual creation assistant skilled in multimodal image analysis and reasoning.

[Task]
Your core task is to intelligently select the most suitable reference images from a provided reference image library (including multiple character reference images and existing scene images from prior frames) based on the user's text description (describing the target frame), ensuring that the subsequently generated image meets the following key consistencies:
- Character Consistency: The appearance (e.g. gender, ethnicity, age, facial features, hairstyle, body shape), clothing, expression, posture, etc., of the generated character should highly match the reference images.
- Environmental Consistency: The scene of the generated image (e.g., background, lighting, atmosphere, layout) should remain coherent with the existing images from prior frames.
- Style Consistency: The visual style of the generated image (e.g., realistic, cartoon, film-like, color tone) should harmonize with the reference images and existing images.

[Input]
You will receive a text description of the target frame, along with a sequence of reference images.
- The text description of the target frame is enclosed within <FRAME_DESC> and </FRAME_DESC>.
- The sequence of reference images is enclosed within <SEQ_IMAGES> and </SEQ_IMAGES>. Each reference image is provided with a text description. The reference images are indexed starting from 0.

Below is an example of the input format:
<FRAME_DESC>
[Camera 1] Shot from Alice's over-the-shoulder perspective. <Alice> is on the side closer to the camera, with only her shoulder appearing in the lower left corner of the frame. <Bob> is on the side farther from the camera, positioned slightly right of center in the frame. <Bob>'s expression shifts from surprise to delight as he recognizes <Alice>.
</FRAME_DESC>

<SEQ_IMAGES>
Image 0: A front-view portrait of Alice.
[Image 0 here]
Image 1: A front-view portrait of Bob.
[Image 1 here]
Image 2: [Camera 0] Medium shot of the supermarket aisle. Alice and Bob are shown in profile facing the right side of the frame. Bob is on the right side of the frame, and Alice is on the left side. Alice, looking down and pushing a shopping cart, follows closely behind Bob and accidentally bumps into his heel.
[Image 2 here]
Image 3: [Camera 1] Shot from Alice's over-the-shoulder perspective. Alice is on the side closer to the camera, with only her shoulder appearing in the lower left corner of the frame. Bob is on the side farther from the camera, positioned slightly right of center in the frame. Bob is back to the camera.
[Image 3 here]
Image 4: [Camera 2] Shot from Bob's over-the-shoulder perspective. Bob is on the side closer to the camera, with only his shoulder appearing in the lower right corner of the frame. Alice is on the side farther from the camera, positioned slightly left of center in the frame. Alice looks down, then up as she prepares to apologize. Upon realizing it's someone familiar, her expression shifts to one of surprise.
</SEQ_IMAGES>

[Output]
You need to select the most relevant reference images based on the user's description and put the corresponding indices in the `ref_image_indices` field of the output. At the same time, you should generate a text prompt that describes the image to be created, specifying which elements in the generated image should reference which image (and which elements within it).

{format_instructions}


[Guidelines]
- Ensure that the language of all output values (not include keys) matches that used in the frame description.
- Character/Prop Consistency: Highly match characters and key objects from reference images.
- Environmental Continuity: Reference previous frame backgrounds and visual anchors.
- Style Harmony: Maintain a consistent cinematic look and color grade.
- Prioritize image descriptions with similar compositions (same camera).
- Prioritize more recent images from prior frames.
- Select at most **8** optimal reference images.
- PASS-THROUGH LOGIC: If the scene background was established in Image X, the prompt MUST state "Maintain the background from Image X" to ensure it passes through the cut.
- Clearly specify in the `text_prompt` which elements should be "Maintained from Image X" (e.g., background, specific prop).
"""


human_prompt_template_select_reference_images = \
"""
<FRAME_DESC>
{frame_description}
</FRAME_DESC>
"""




class RefImageIndicesAndTextPrompt(BaseModel):
    ref_image_indices: List[int] = Field(
        description="Indices of reference images selected from the provided images. For example, [0, 2, 5] means selecting the first, third, and sixth images. The indices should be 0-based.",
        examples=[
            [1, 3]
        ]
    )
    text_prompt: str = Field(
        description="Text description to guide the image generation. You need to describe the image to be generated, specifying which elements in the generated image should reference which image (and which elements within it). For example, 'Create an image following the given description: \nThe man is standing in the landscape. The man should reference Image 0. The landscape should reference Image 1.' Here, the index of the reference image should refer to its position in the ref_image_indices list, not the sequence number in the provided image list. Refer to the reference image must be in the format of Image N. Do not use any other word except Image.",
        examples=[
            "Create an image based on the following guidance: \n Make modifications based on Image 1: Bob's body turns to face the camera, while all other elements remain unchanged. Bob's appearance should refer to Image 0.",
            "Create an image following the given description: \nThe man is standing in the landscape. The man should reference Image 0. The landscape should reference Image 1."
        ]
    )



class ReferenceImageSelector:
    def __init__(
        self,
        chat_model,
    ):

        self.chat_model = chat_model


    @retry(
        stop=stop_after_attempt(3),
        after=after_func,
    )
    async def select_reference_images_and_generate_prompt(
        self,
        available_image_path_and_text_pairs: List[Tuple[str, str]],
        frame_description: str,
        establishment_frame_path: Optional[str] = None,
    ):
        filtered_image_path_and_text_pairs = available_image_path_and_text_pairs

        # 1. filter images using text-only model
        if len(available_image_path_and_text_pairs) >= 8:
            human_content = []
            for idx, (_, text) in enumerate(available_image_path_and_text_pairs):
                human_content.append({
                    "type": "text",
                    "text": f"Image {idx}: {text}"
                })
            human_content.append({
                "type": "text",
                "text": human_prompt_template_select_reference_images.format(frame_description=frame_description)
            })
            parser = PydanticOutputParser(pydantic_object=RefImageIndicesAndTextPrompt)

            messages = [
                SystemMessage(content=system_prompt_template_select_reference_images_only_text.format(format_instructions=parser.get_format_instructions())),
                HumanMessage(content=human_content)
            ]

            chain = self.chat_model | parser

            try:
                ref = await chain.ainvoke(messages)
                filtered_image_path_and_text_pairs = [available_image_path_and_text_pairs[i] for i in ref.ref_image_indices]
                logging.info(f"Filtered image idx:{ref.ref_image_indices}")
                
            except Exception as e:
                logging.error(f"Error get image prompt: \n{e}")
                raise e

        # 2. filter images using multimodal model
        human_content = []
        if establishment_frame_path and os.path.exists(establishment_frame_path):
            human_content.append({
                "type": "text",
                "text": "ESTABLISHMENT IMAGE (MASTER REFERENCE): Maintain this exact background and lighting."
            })
            human_content.append({
                "type": "image_url",
                "image_url": {"url": image_path_to_b64(establishment_frame_path)}
            })

        for idx, (image_path, text) in enumerate(filtered_image_path_and_text_pairs):
            human_content.append({
                "type": "text",
                "text": f"Image {idx}: {text}"
            })
            # Only add image if path exists and is not empty
            if image_path and os.path.exists(image_path):
                human_content.append({
                    "type": "image_url",
                    "image_url": {"url": image_path_to_b64(image_path)}
                })
            else:
                # For props or text-only references, skip the image but keep the text description
                logging.debug(f"Skipping image for path '{image_path}' (empty or not found), using text-only reference")
        human_content.append({
            "type": "text",
            "text": human_prompt_template_select_reference_images.format(frame_description=frame_description)
        })

        parser = PydanticOutputParser(pydantic_object=RefImageIndicesAndTextPrompt)

        messages = [
            SystemMessage(content=system_prompt_template_select_reference_images_multimodal.format(format_instructions=parser.get_format_instructions())),
            HumanMessage(content=human_content)
        ]

        chain = self.chat_model | parser

        try:
            response = await chain.ainvoke(messages)        
            reference_image_path_and_text_pairs = [filtered_image_path_and_text_pairs[i] for i in response.ref_image_indices]
            return {
                "reference_image_path_and_text_pairs": reference_image_path_and_text_pairs,
                "text_prompt": response.text_prompt,
            }

        except Exception as e:
            logging.error(f"Error get image prompt: \n{e}")
            raise e


