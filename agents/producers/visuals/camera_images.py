import os
import logging
import cv2
from typing import List, Tuple, Union, Optional
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from scenedetect import open_video, SceneManager, split_video_ffmpeg
from scenedetect.detectors import ContentDetector

from agents.base import BaseAgent
from interfaces import ShotDescription, ShotBriefDescription, Camera, ImageOutput, VideoOutput


from moviepy import VideoFileClip
from PIL import Image


system_prompt_template_select_reference_camera = \
"""
[Role]
You are a professional video editing expert specializing in multi-camera shot analysis and scene structure modeling. You have deep knowledge of cinematic language, enabling you to understand shot sizes (e.g., wide shot, medium shot, close-up) and content inclusion relationships. You can infer hierarchical structures between camera positions based on corresponding shot descriptions.

[Task]
Your task is to analyze the input camera position data to construct a "camera position tree". This tree structure represents a relationship where a parent camera's content encompasses that of a child camera. Specifically, you need to identify the parent camera for each camera position (if one exists) and determine the dependent shot indices (i.e., the specific shots within the parent camera's footage that contain the child camera's content). If a camera position has no parent, output None.

[Input]
The input is a sequence of cameras. The sequence will be enclosed within <CAMERA_SEQ> and </CAMERA_SEQ>.
Each camera contains a sequence of shots filmed by the camera, which will be enclosed within <CAMERA_N> and </CAMERA_N>, where N is the index of the camera.

Below is an example of the input format:

<CAMERA_SEQ>
<CAMERA_0>
Shot 0: Medium shot of the street. Alice and Bob are walking towards each other.
Shot 2: Medium shot of the street. Alice and Bob hug each other.
</CAMERA_0>
<CAMERA_1>
Shot 1: Close-up of the Alice's face. Her expression shifts from surprise to delight as she recognizes Bob.
</CAMERA_1>
</CAMERA_SEQ>


[Output]
{format_instructions}

[Guidelines]
- The language of all output values (not include keys) should be consistent with the language of the input.
- Content Inclusion Check: The parent camera should as fully as possible contain the child camera's content in certain shots (e.g., a parent medium two-shot encompasses a child over-the-shoulder reverse shot). Analyze shot descriptions by comparing keywords (e.g., characters, actions, setting) to ensure the parent shot's field of view covers the child shot's.
- Transition Smoothness Priority: Larger shot size as parent camera is preferred, such as Wide Shot -> Medium Shot or Medium Shot -> Close-up. The shot sizes of adjacent parent and child nodes should be as similar as possible. A direct transition from a long shot to a close-up is not allowed unless absolutely necessary.
- Temporal Proximity: Each camera is described by its corresponding first shot, and the parent camera is located based on the description of the first shot. The shot index of the parent camera should be as close as possible to the first shot index of the child camera.
- Logical Consistency: The camera tree should be acyclic, avoid circular dependencies. If a camera is contained by multiple potential parents, select the best match (based on shot size and content). If there is no suitable parent camera, output None.
- When a broader perspective is not available, choose the shot with the largest overlapping field of view as the parent (the one with the most information overlap), or a shot can also serve as the parent of a reverse shot. When two cameras can be the parent of each other, choose the one with the smaller index as the parent of the camera with the larger index.
- Only one camera can exist without a parent.
- When describing the elements lost in a shot, carefully compare the details between the parent shot and the child shot. For example, the parent shot is a medium shot of Character A and Character B facing each other (both in profile to the camera), while the child shot is a close-up of Character A (with Character A facing the camera directly). In this case, the child shot lacks the frontal view information of Character A.
- The first camera must be the root of the camera tree.
"""


human_prompt_template_select_reference_camera = \
"""
<CAMERA_SEQ>
{camera_seq_str}
</CAMERA_SEQ>
"""


class CameraParentItem(BaseModel):
    parent_cam_idx: Optional[int] = Field( 
        default=None, 
        description="The index of the parent camera. Set to None if the camera has no parent (e.g., for a root camera).",
        examples=[0, 1, None], 
    )
    parent_shot_idx: Optional[int] = Field( 
        default=None, 
        description="The index of the dependent shot. Set to None if the camera has no parent (e.g., for a root camera).",
        examples=[0, 3, None], 
    )
    reason: str = Field(
        description="The reason for the selection of the parent camera. If the camera has no parent, it should explain why it's a root camera.",
        examples=[
            "The parent shot's field of view covers the child shot's field of view (from medium shot to close-up)",
            "The parent shot and the child shot have a shot/reverse shot relationship.",
            "CAMERA_0 (Shot 0) establishes the entire scene and contains all characters and the setting. It is the root camera." # 补充 LLM 实际输出的例子
        ],
    )
    is_parent_fully_covers_child: Optional[bool] = Field( 
        default=None, 
        description="Whether the parent camera fully covers the child camera's content. Set to None if the camera has no parent.",
        examples=[True, False, None], 
    )
    missing_info: Optional[str] = Field(
        default=None,
        description="The missing elements in the child shot that are not covered by the parent shot. If the parent shot fully covers the child shot, set this to None.",
        examples=[
            "The frontal view of Alice.",
            None,
        ],
    )

class CameraTreeResponse(BaseModel):
    camera_parent_items: List[Optional[CameraParentItem]] = Field(
        description="The parent camera items for each camera. If a camera has no parent, set this to None. The length of the list should be the same as the number of cameras.",
    )



CAMERA_ANALYSIS_PROFILES = {
    "feature_film": system_prompt_template_select_reference_camera,
    "short_film": system_prompt_template_select_reference_camera,
    "tv_series": """
[Role]
You are an expert TV series editor and multicam specialist. You excel at identifying parent-child camera relationships across episodic content, ensuring seamless transitions and consistent character positioning within sets.

[Task]
Analyze the input camera sequence to construct a "camera tree" for a TV series episode.

[Guidelines]
- EPISODIC FLOW: Parent cameras should establish the geography of the set.
- BACKGROUND LOCK: Every camera must prioritize maintaining the exact background established in the parent camera. 
- VISUAL ANCHORS: Explicitly reference and maintain visual anchors (props or background features) across shots.
- DIALOGUE DYNAMICS: Child cameras (close-ups) must be correctly parented to master shots (two-shots or wide shots) containing the conversation.
- CONSISTENCY: Prioritize camera angles that maintain the "180-degree rule" for narrative clarity.
""",
    "documentary": """
[Role]
You are an elite documentary film editor. You specialize in "Visual Evidence" and "Spatial Truth" - ensuring that every camera angle transition feels authentic and supports the narrative claim.

[Task]
Construct a camera tree for a documentary segment.

[Guidelines]
- AUTHENTIC TRANSITIONS: Wide establishing shots must encompass the detailed evidence or interview subjects shown in child cameras.
- SPATIAL TRUTH: Ensure child cameras represent subsets of the world shown in parent cameras.
- B-ROLL HIERARCHY: Group related B-roll shots under a common visual theme or location parent.
""",
    "learning_series": """
[Role]
You are a lead educational video producer. You specialize in "Pedagogical Flow" - ensuring that visual transitions guide the learner's attention effectively.

[Task]
Construct a camera tree for an educational episode.

[Guidelines]
- ATTENTION MANAGEMENT: Establishing wide shots of the whiteboard or instructor must serve as parents to close-ups of specific diagrams or code.
- PEDAGOGICAL CONTINUITY: Transitions between different segments (Hook -> Teach) should be logical and visually connected.
""",
    "podcast": """
[Role]
You are an elite multicam video podcast editor. You specialize in "Conversation Continuity" and "Reaction Dynamics."

[Task]
Construct a camera tree for a video podcast.

[Guidelines]
- STUDIO GEOGRAPHY: The wide "Studio Shot" is the root. Medium "Two-Shots" and tight "Reaction Shots" must be parented correctly to the wide shot.
- INTERACTION FOCUS: Ensure child cameras are parented to the camera that best captures the interaction.
""",
    "ad": """
[Role]
You are a top-tier commercial film editor. You specialize in "Relentless Pacing" and "Visual Impact."

[Task]
Construct a camera tree for a high-impact advertisement.

[Guidelines]
- IMPACT HIERARCHY: Every child camera must provide a more intense or detailed view of the "Hero" established in the parent camera.
- SPEED: Prioritize similar camera positions to enable rapid, high-speed cutting.
""",
    "music_video": """
[Role]
You are a visionary music video editor. You specialize in "Rhythmic Hierarchy" and "Symbolic Transitions."

[Task]
Construct a camera tree for a music video.

[Guidelines]
- RHYTHMIC PARENTING: Use experimental angles as parents if they establish the visual theme of the sequence.
- SYMBOLIC CONTINUITY: Ensure child cameras advance the visual metaphor established in the parent shot.
"""
}

class CameraImageGenerator(BaseAgent):

    def __init__(
        self,
        chat_model,
        image_generator,
        video_generator,
        pipeline_kind: str = "feature_film"
    ):
        super().__init__(chat_model)
        self.image_generator = image_generator
        self.video_generator = video_generator
        self.pipeline_kind = pipeline_kind if pipeline_kind in CAMERA_ANALYSIS_PROFILES else "feature_film"


    async def construct_camera_tree(
        self,
        cameras: List[Camera],
        shot_descs: List[Union[ShotDescription, ShotBriefDescription]],
    ) -> List[Camera]:
        parser = PydanticOutputParser(pydantic_object=CameraTreeResponse)

        camera_seq_str = "<CAMERA_SEQ>\n"
        for cam in cameras:
            camera_seq_str += f"<CAMERA_{cam.idx}>\n"
            for shot_idx in cam.active_shot_idxs:
                camera_seq_str += f"Shot {shot_idx}: {shot_descs[shot_idx].visual_desc}\n"
            camera_seq_str += f"</CAMERA_{cam.idx}>\n"
        camera_seq_str += "</CAMERA_SEQ>"

        # Select profile
        system_prompt = CAMERA_ANALYSIS_PROFILES.get(self.pipeline_kind, system_prompt_template_select_reference_camera)

        messages = [
            SystemMessage(content=system_prompt.format(format_instructions=parser.get_format_instructions()) if "{format_instructions}" in system_prompt else f"{system_prompt}\n\n[Output Format]\n{parser.get_format_instructions()}"),
            HumanMessage(content=human_prompt_template_select_reference_camera.format(camera_seq_str=camera_seq_str)),
        ]

        response = await self.chat_model.ainvoke(messages)
        parsed = await self.parse_with_repair(response.content, CameraTreeResponse)
        for cam, parent_cam_item in zip(cameras, parsed.camera_parent_items):
            cam.parent_cam_idx = parent_cam_item.parent_cam_idx if parent_cam_item is not None else None
            cam.parent_shot_idx = parent_cam_item.parent_shot_idx if parent_cam_item is not None else None
            cam.reason = parent_cam_item.reason if parent_cam_item is not None else None
            cam.parent_shot_idx = parent_cam_item.parent_shot_idx if parent_cam_item is not None else None
            cam.is_parent_fully_covers_child = parent_cam_item.is_parent_fully_covers_child if parent_cam_item is not None else None
            cam.missing_info = parent_cam_item.missing_info if parent_cam_item is not None else None
        return cameras


    async def generate_transition_video(
        self,
        first_shot_visual_desc: str,
        second_shot_visual_desc: str,
        first_shot_ff_path: str,
        output_dir: Optional[str] = None,
    ) -> VideoOutput:

        prompt = f"Two shots. The transition between the shots is a cut to. The style of the two shots should be consistent."
        prompt += f"\nThe first shot description: {first_shot_visual_desc}."
        prompt += f"\nThe second shot description: {second_shot_visual_desc}."
        reference_image_paths = [first_shot_ff_path]

        if output_dir:
            debug_dir = os.path.join(output_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            with open(os.path.join(debug_dir, "transition_video_prompt.txt"), "w", encoding="utf-8") as f:
                f.write(prompt)

        video_output = await self.video_generator.generate_single_video(
            prompt=prompt,
            reference_image_paths=reference_image_paths,
        )
        return video_output


    def get_new_camera_image(
        self,
        transition_video_path: str,
    ) -> ImageOutput:
        video = open_video(transition_video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector())
        scene_manager.detect_scenes(video, show_progress=False)
        scene_list = scene_manager.get_scene_list()
        output_dir = os.path.join(os.path.dirname(transition_video_path), "cache")
        os.makedirs(output_dir, exist_ok=True)
        split_video_ffmpeg(transition_video_path, scene_list, output_dir, show_progress=True)


        video_name = os.path.basename(transition_video_path).split('.')[0]
        second_video_path = os.path.join(output_dir, f"{video_name}-Scene-002.mp4")
        if os.path.exists(second_video_path):
            # use first frame of second shot as new camera image
            clip = VideoFileClip(second_video_path)
            ff = clip.get_frame(0)
            ff = Image.fromarray(ff.astype('uint8'), 'RGB')
            return ImageOutput(fmt="pil", ext="png", data=ff)
        else:
            # use last frame of transition video to instead
            clip = VideoFileClip(transition_video_path)
            lf_time = clip.duration - (1 / clip.fps)
            lf_time = max(0, lf_time)
            lf = clip.get_frame(lf_time)
            lf = Image.fromarray(lf.astype('uint8'), 'RGB')
            return ImageOutput(fmt="pil", ext="png", data=lf)


    async def generate_first_frame(
        self,
        shot_desc: ShotDescription,
        character_portrait_path_and_text_pairs: List[Tuple[str, str]],
    ) -> ImageOutput:
        prompt = ""
        reference_image_paths = []
        for i,(path, text )in enumerate(character_portrait_path_and_text_pairs):
            prompt += f"Image {i}: {text}\n"
            reference_image_paths.append(path)
        prompt += f"Generate an image based on the following description: {shot_desc.ff_desc}."
        image_output = await self.image_generator.generate_single_image(
            prompt=prompt,
            reference_image_paths=reference_image_paths,
            size="1600x900",
        )
        return image_output