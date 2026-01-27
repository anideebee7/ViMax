import logging
import requests
import base64
import mimetypes
import os
import re
from typing import Optional, Tuple, List
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from io import BytesIO
import cv2
import numpy as np
from PIL import Image

try:
    import boto3
    from botocore.exceptions import NoCredentialsError, ClientError
except ImportError:
    boto3 = None


def _parse_s3_url(url: str) -> Optional[Tuple[str, str, Optional[str]]]:
    """Parse S3 URL into bucket, key, and optional region."""
    if url.startswith("s3://"):
        parts = url[5:].split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1], None

    # Standard S3 HTTP URL: https://bucket.s3.region.amazonaws.com/key
    match = re.match(r"https://([^.]+)\.s3\.([^.]+)\.amazonaws\.com/(.*)", url)
    if match:
        return match.group(1), match.group(3), match.group(2)

    # S3 URL without region: https://bucket.s3.amazonaws.com/key
    match = re.match(r"https://([^.]+)\.s3\.amazonaws\.com/(.*)", url)
    if match:
        return match.group(1), match.group(2), None

    # S3 URL with bucket in path: https://s3.region.amazonaws.com/bucket/key
    match = re.match(r"https://s3\.([^.]+)\.amazonaws\.com/([^/]+)/(.*)", url)
    if match:
        return match.group(2), match.group(3), match.group(1)

    # S3 URL with bucket in path, no region: https://s3.amazonaws.com/bucket/key
    match = re.match(r"https://s3\.amazonaws\.com/([^/]+)/(.*)", url)
    if match:
        return match.group(1), match.group(2), None

    return None


def _download_from_s3(
    bucket: str, key: str, save_path: str, region: Optional[str] = None
) -> bool:
    """Download file from S3 using boto3."""
    if boto3 is None:
        logging.warning("boto3 not installed, cannot download from S3")
        return False

    try:
        s3 = boto3.client("s3", region_name=region)
        s3.download_file(bucket, key, save_path)
        return True
    except (NoCredentialsError, ClientError) as e:
        logging.warning(f"S3 download failed for s3://{bucket}/{key}: {e}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error downloading from S3: {e}")
        return False


def _is_not_404(exception):
    """Return True if the exception is NOT a 404 error."""
    if isinstance(exception, requests.exceptions.HTTPError):
        return exception.response.status_code != 404
    if boto3 and isinstance(exception, ClientError):
        return exception.response["Error"]["Code"] != "404"
    return True


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception(_is_not_404),
    reraise=True
)
def download_image(url, save_path):
    try:
        logging.info(f"Downloading image from {url} to {save_path}")

        # Try S3 first if it looks like an S3 URL
        s3_info = _parse_s3_url(url)
        if s3_info:
            bucket, key, region = s3_info
            if _download_from_s3(bucket, key, save_path, region):
                logging.info(f"Image downloaded successfully from S3 to {save_path}")
                return

        # Fallback to HTTP download
        response = requests.get(url, stream=True)
        response.raise_for_status()  # Check for HTTP errors

        with open(save_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=1024):
                file.write(chunk)
        logging.info(f"Image downloaded successfully via HTTP to {save_path}")

    except Exception as e:
        logging.error(f"Error downloading image: {e}")
        raise e


def image_path_to_b64(image_path, mime: bool = True) -> str:
    with open(image_path, 'rb') as image_file:
        b64 = base64.b64encode(image_file.read()).decode('utf-8')

    if mime:
        mime_type, _ = mimetypes.guess_type(image_path)
        if mime_type is None:
            mime_type = 'application/octet-stream'
        return f"data:{mime_type};base64,{b64}"

    return b64


def pil_to_b64(image, mime: bool = True) -> str:
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

    if mime:
        return f"data:image/png;base64,{b64}"

    return b64


def save_base64_image(b64_string, save_path):
    # If the base64 string has a data URL prefix, remove it
    if ',' in b64_string:
        b64_string = b64_string.split(',')[1]

    with open(save_path, 'wb') as image_file:
        image_file.write(base64.b64decode(b64_string))


# =============================================================================
# Character Compositing Functions
# =============================================================================

def composite_character_on_image(
    background_path: str,
    character_path: str,
    output_path: Optional[str] = None,
    position: str = "center",
    scale_factor: float = 0.4,
    vertical_offset: float = 0.1,
    blend_mode: str = "normal",
    auto_remove_bg: bool = True,
) -> str:
    """
    Composite a character portrait onto a background scene image.
    
    This ensures S3 character images are used exactly as designed,
    since AI image generators cannot reliably reproduce character designs
    from reference images alone.
    
    Args:
        background_path: Path to the background/scene image
        character_path: Path to the character portrait image
        output_path: Output path (defaults to overwriting background)
        position: Character position - "center", "left", "right", "center-left", "center-right"
        scale_factor: Character size relative to image height (0.0-1.0)
        vertical_offset: Vertical position offset from bottom (0.0-1.0)
        blend_mode: Blending mode - "normal", "soft", "overlay"
        auto_remove_bg: Automatically remove solid background from character
    
    Returns:
        Path to the output image
    """
    if output_path is None:
        output_path = background_path
    
    try:
        # Open images
        background = Image.open(background_path).convert("RGBA")
        character_img = Image.open(character_path)
        
        # Auto-remove background from character portrait
        if auto_remove_bg:
            character = _remove_solid_background(character_img)
        else:
            character = character_img.convert("RGBA")
        
        bg_width, bg_height = background.size
        char_width, char_height = character.size
        
        # Calculate character size (scaled to scene)
        target_height = int(bg_height * scale_factor)
        aspect_ratio = char_width / char_height
        target_width = int(target_height * aspect_ratio)
        
        # Resize character
        character = character.resize((target_width, target_height), Image.Resampling.LANCZOS)
        
        # Calculate position
        if position == "center":
            x = (bg_width - target_width) // 2
        elif position == "left":
            x = int(bg_width * 0.1)
        elif position == "right":
            x = bg_width - target_width - int(bg_width * 0.1)
        elif position == "center-left":
            x = int(bg_width * 0.25) - target_width // 2
        elif position == "center-right":
            x = int(bg_width * 0.75) - target_width // 2
        else:
            x = (bg_width - target_width) // 2
        
        # Vertical position (from bottom, offset upward)
        y = bg_height - target_height - int(bg_height * vertical_offset)
        
        # Apply soft edge blending if requested
        if blend_mode == "soft":
            character = _apply_soft_edge(character, edge_width=15)
        
        # Composite character onto background
        background.paste(character, (x, y), character)
        
        # Convert to RGB and save
        final = background.convert("RGB")
        final.save(output_path)
        
        logging.info(f"Composited character onto image: {output_path}")
        return output_path
        
    except Exception as e:
        logging.warning(f"Failed to composite character: {e}")
        return background_path


def composite_multiple_characters(
    background_path: str,
    character_paths: List[str],
    output_path: Optional[str] = None,
    positions: Optional[List[str]] = None,
    scale_factors: Optional[List[float]] = None,
    auto_remove_bg: bool = True,
    character_names: Optional[List[str]] = None,
) -> str:
    """
    Composite multiple character portraits onto a background scene.
    """
    if output_path is None:
        output_path = background_path
    
    if not character_paths:
        return background_path
    
    # Default positions based on character count
    if positions is None:
        if len(character_paths) == 1:
            positions = ["center"]
        elif len(character_paths) == 2:
            positions = ["center-left", "center-right"]
        elif len(character_paths) == 3:
            positions = ["left", "center", "right"]
        else:
            positions = ["left"] + ["center"] * (len(character_paths) - 2) + ["right"]
    
    # Default scale factors
    if scale_factors is None:
        base_scale = 0.4 if len(character_paths) == 1 else 0.35
        scale_factors = [base_scale] * len(character_paths)
    
    try:
        # Load background and ensure it's RGBA
        background = Image.open(background_path).convert("RGBA")
        bg_width, bg_height = background.size
        
        # Track which characters were successfully composited
        composited_count = 0
        
        for i, char_path in enumerate(character_paths):
            if not os.path.exists(char_path):
                logging.warning(f"Character portrait not found: {char_path}")
                continue
            
            char_name = character_names[i] if character_names and i < len(character_names) else f"Char_{i}"
            logging.info(f"Compositing character {i}: {char_name} from {char_path}")
            
            # Load character portrait
            char_img = Image.open(char_path)
            
            # Auto-remove background from character portrait
            if auto_remove_bg:
                # We pass a flag to tell if it's likely a white character to be more careful
                is_autocurio = "autocurio" in char_name.lower() or "curio" in char_name.lower()
                character = _remove_solid_background(char_img, tolerance=15 if is_autocurio else 30)
            else:
                character = char_img.convert("RGBA")
            
            char_width, char_height = character.size
            
            # Scale character
            scale = scale_factors[i] if i < len(scale_factors) else 0.35
            target_height = int(bg_height * scale)
            aspect_ratio = char_width / char_height
            target_width = int(target_height * aspect_ratio)
            
            character = character.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Position character
            pos = positions[i] if i < len(positions) else "center"
            
            # X coordinate logic
            if pos == "center":
                x = (bg_width - target_width) // 2
            elif pos == "left":
                x = int(bg_width * 0.05)
            elif pos == "right":
                x = bg_width - target_width - int(bg_width * 0.05)
            elif pos == "center-left":
                x = int(bg_width * 0.2)
            elif pos == "center-right":
                x = bg_width - target_width - int(bg_width * 0.2)
            else:
                x = (bg_width - target_width) // 2
            
            # Y coordinate (keep characters on the ground)
            y = bg_height - target_height - int(bg_height * 0.05)
            
            # Apply soft edge for natural blending
            character = _apply_soft_edge(character, edge_width=10)
            
            # Composite using alpha channel as mask
            background.paste(character, (x, y), character)
            composited_count += 1
        
        # Save result as RGB (final image)
        final = background.convert("RGB")
        final.save(output_path)
        
        logging.info(f"Successfully composited {composited_count} characters onto image: {output_path}")
        return output_path
    
    except Exception as e:
        logging.warning(f"Failed to composite multiple characters: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return background_path


def _apply_soft_edge(image: Image.Image, edge_width: int = 10) -> Image.Image:
    """Apply soft edge feathering to character for natural blending."""
    try:
        # Get alpha channel
        if image.mode != "RGBA":
            return image
        
        r, g, b, a = image.split()
        
        # Apply slight feathering to alpha edges
        from PIL import ImageFilter
        a = a.filter(ImageFilter.GaussianBlur(radius=edge_width // 3))
        
        return Image.merge("RGBA", (r, g, b, a))
    except Exception:
        return image


def _remove_solid_background(image: Image.Image, tolerance: int = 30) -> Image.Image:
    """
    Remove solid/near-white background from a character portrait.
    
    This handles RGB images or RGBA images with solid alpha by detecting the 
    background color from corners and making it transparent.
    """
    try:
        # 1. Check if it already has meaningful transparency
        if image.mode == "RGBA":
            alpha = image.getchannel("A")
            extrema = alpha.getextrema()
            # If the minimum alpha is < 200, assume it's already a transparent PNG
            if extrema[0] < 200:
                return image
        
        rgba_img = image.convert("RGBA")
        width, height = rgba_img.size
        
        # 2. Detect background color by sampling CORNERS
        # We sample a 5x5 block in each corner and use the median to avoid noise
        corners = [
            rgba_img.crop((0, 0, 5, 5)),
            rgba_img.crop((width-5, 0, width, 5)),
            rgba_img.crop((0, height-5, 5, height)),
            rgba_img.crop((width-5, height-5, width, height))
        ]
        
        corner_colors = []
        for c in corners:
            # Get average color of this corner block
            data = np.array(c)
            avg = np.mean(data[:, :, :3], axis=(0, 1))
            corner_colors.append(tuple(avg.astype(int)))
            
        # Use the most common corner color
        from collections import Counter
        # Convert to standard python ints to avoid numpy type issues in Counter/logging
        corner_colors_list = [tuple(map(int, color)) for color in corner_colors]
        bg_color = Counter(corner_colors_list).most_common(1)[0][0]
        
        # 3. CRITICAL: Is this a white character on a white background? (e.g. Autocurio)
        is_light_bg = sum(bg_color) > 600
        
        data = np.array(rgba_img)
        rgb_data = data[:, :, :3]
        
        # Calculate color distance
        # Convert bg_color to numpy array for vector subtraction
        bg_color_np = np.array(bg_color)
        dist = np.sqrt(np.sum((rgb_data - bg_color_np)**2, axis=2))
        
        # 4. Create mask
        # If it's a light background, we use a slightly higher tolerance but keep it tight
        # to protect light-colored character bodies (like white robots).
        if is_light_bg:
            # Increased from 10 to 25 to handle noise/compression artifacts better
            effective_tolerance = 25
            
            # Use a soft ramp for smoother edges
            # Pixels within [0, tolerance] are transparent
            # Pixels within [tolerance, tolerance*2] are partially transparent
            mask = np.ones(dist.shape, dtype=np.uint8) * 255
            mask[dist < effective_tolerance] = 0
            
            # Apply a bit of smoothing to the mask to avoid jagged edges
            # We use PIL's Gaussian blur on the alpha channel later for this.
            new_alpha = mask
        else:
            # Normal tolerance for dark/colored backgrounds
            effective_tolerance = tolerance
            new_alpha = np.where(dist < effective_tolerance, 0, 255).astype(np.uint8)
            # Add a smooth ramp for non-white characters
            ramp_mask = (dist >= effective_tolerance) & (dist < effective_tolerance * 1.5)
            ramp_values = ((dist[ramp_mask] - effective_tolerance) / (effective_tolerance * 0.5) * 255).astype(np.uint8)
            new_alpha[ramp_mask] = ramp_values
        
        data[:, :, 3] = new_alpha
        
        # 5. Clean up the mask: Use a morphological opening to remove small isolated dots
        # and closing to fill small holes inside the character if needed.
        # Since we use numpy, we can do a simple erosion/dilation if needed, 
        # but PIL's filter is often safer for general use.
        
        result = Image.fromarray(data, "RGBA")
        
        # Apply a slight blur to the alpha channel to soften the edges
        if is_light_bg:
            r, g, b, a = result.split()
            from PIL import ImageFilter
            a = a.filter(ImageFilter.MaxFilter(3)) # Slight expansion to avoid cutting into character
            a = a.filter(ImageFilter.GaussianBlur(radius=1))
            result = Image.merge("RGBA", (r, g, b, a))
            
        logging.info(f"Removed solid background (detected color: {bg_color}, light_bg: {is_light_bg})")
        return result
            
    except Exception as e:
        logging.warning(f"Background removal failed: {e}")
        return image.convert("RGBA")


def composite_logo_on_image(
    background_path: str,
    logo_path: str,
    output_path: Optional[str] = None,
    position: str = "top-right",
    scale_factor: float = 0.15,
    padding: float = 0.05,
    auto_remove_bg: bool = True,
) -> str:
    """
    Composite a logo or app icon onto an image.
    
    Args:
        background_path: Path to the background image
        logo_path: Path to the logo/icon image
        output_path: Output path
        position: "top-right", "top-left", "bottom-right", "bottom-left", "center"
        scale_factor: Logo size relative to image width
        padding: Padding from edges as percentage of image size
        auto_remove_bg: Automatically remove solid background from logo
    """
    if output_path is None:
        output_path = background_path
    
    if not os.path.exists(logo_path):
        return background_path
        
    try:
        background = Image.open(background_path).convert("RGBA")
        logo_img = Image.open(logo_path)
        
        if auto_remove_bg:
            logo = _remove_solid_background(logo_img)
        else:
            logo = logo_img.convert("RGBA")
            
        bg_w, bg_height = background.size
        l_w, l_h = logo.size
        
        # Scale logo relative to background width
        target_w = int(bg_w * scale_factor)
        aspect = l_h / l_w
        target_h = int(target_w * aspect)
        
        logo = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        pad_x = int(bg_w * padding)
        pad_y = int(bg_height * padding)
        
        if position == "top-right":
            x, y = bg_w - target_w - pad_x, pad_y
        elif position == "top-left":
            x, y = pad_x, pad_y
        elif position == "bottom-right":
            x, y = bg_w - target_w - pad_x, bg_height - target_h - pad_y
        elif position == "bottom-left":
            x, y = pad_x, bg_height - target_h - pad_y
        else: # center
            x, y = (bg_w - target_w) // 2, (bg_height - target_h) // 2
            
        background.paste(logo, (x, y), logo)
        background.convert("RGB").save(output_path)
        
        logging.info(f"Composited logo onto image at {position}: {output_path}")
        return output_path
    except Exception as e:
        logging.warning(f"Failed to composite logo: {e}")
        return background_path


def remove_background_simple(image_path: str, output_path: Optional[str] = None) -> str:
    """
    Simple background removal for character portraits with solid/simple backgrounds.
    
    For more complex backgrounds, consider using rembg or similar libraries.
    
    Args:
        image_path: Path to the character image
        output_path: Output path (defaults to same path)
    
    Returns:
        Path to the output image with transparent background
    """
    if output_path is None:
        output_path = image_path
    
    try:
        img = Image.open(image_path).convert("RGBA")
        width, height = img.size
        pixels = img.load()
        
        # Sample background color from corners
        corner_colors = [
            pixels[0, 0],
            pixels[width - 1, 0],
            pixels[0, height - 1],
            pixels[width - 1, height - 1],
        ]
        
        # Find most common background color
        bg_color = max(set(corner_colors), key=corner_colors.count)
        
        # Create new image with transparency
        new_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        new_pixels = new_img.load()
        
        tolerance = 30  # Color difference tolerance
        
        for y in range(height):
            for x in range(width):
                pixel = pixels[x, y]
                # Check if pixel is close to background color
                diff = sum(abs(pixel[i] - bg_color[i]) for i in range(3))
                if diff > tolerance * 3:
                    new_pixels[x, y] = pixel
        
        new_img.save(output_path)
        logging.info(f"Removed background from: {output_path}")
        return output_path
        
    except Exception as e:
        logging.warning(f"Failed to remove background: {e}")
        return image_path


def get_character_position_from_description(description: str, character_name: Optional[str] = None) -> str:
    """
    Infer character position from visual description.
    
    Args:
        description: Visual description of the shot/frame
        character_name: Optional name of the specific character to find position for
    
    Returns:
        Position string: "left", "center", "right", "center-left", "center-right"
    """
    desc_lower = description.lower()
    
    # If character name is provided, look for position keywords near the name
    if character_name:
        name_lower = character_name.lower()
        if name_lower in desc_lower:
            # Look at a window around the name
            idx = desc_lower.find(name_lower)
            start = max(0, idx - 40)
            end = min(len(desc_lower), idx + len(name_lower) + 40)
            window = desc_lower[start:end]
            
            if any(kw in window for kw in ["on the left", "left side", "at the left", "leftmost"]):
                return "left"
            if any(kw in window for kw in ["on the right", "right side", "at the right", "rightmost"]):
                return "right"
            if any(kw in window for kw in ["center-left", "left of center"]):
                return "center-left"
            if any(kw in window for kw in ["center-right", "right of center"]):
                return "center-right"
            if "center" in window or "middle" in window:
                return "center"

    # Fallback to general position keywords
    if any(kw in desc_lower for kw in ["left side", "on the left", "from left", "leftmost"]):
        return "left"
    elif any(kw in desc_lower for kw in ["right side", "on the right", "from right", "rightmost"]):
        return "right"
    elif any(kw in desc_lower for kw in ["center-left", "left of center", "slightly left"]):
        return "center-left"
    elif any(kw in desc_lower for kw in ["center-right", "right of center", "slightly right"]):
        return "center-right"
    else:
        return "center"


def get_character_scale_from_shot_type(visual_desc: str) -> float:
    """
    Infer character scale from shot type description.
    
    Args:
        visual_desc: Visual description mentioning shot type
    
    Returns:
        Scale factor (0.0-1.0)
    """
    desc_lower = visual_desc.lower()
    
    # Close-up shots = larger character
    if any(kw in desc_lower for kw in ["close-up", "closeup", "close up", "extreme close"]):
        return 0.7
    elif any(kw in desc_lower for kw in ["medium close", "medium shot", "mid-shot"]):
        return 0.5
    elif any(kw in desc_lower for kw in ["wide shot", "wide angle", "establishing", "full shot"]):
        return 0.3
    elif any(kw in desc_lower for kw in ["long shot", "extreme wide"]):
        return 0.25
    else:
        return 0.4  # Default medium scale


# =============================================================================
# Prop Compositing Functions
# =============================================================================

async def generate_transition_frame(
    image_generator,
    previous_frame_path: str,
    current_shot_description: str,
    output_path: str,
    style: str = "cinematic",
    strength: float = 0.4,
) -> Optional[str]:
    """Generate a transition frame between two shots for smooth visual flow.
    
    This creates a visual bridge between shots to avoid abrupt cuts.
    
    Args:
        image_generator: Image generator instance (must have generate_single_image method)
        previous_frame_path: Path to the previous shot's frame
        current_shot_description: Description of the current shot
        output_path: Path to save the transition frame
        style: Visual style for the transition
        strength: Blending strength (0.0-1.0, lower = smoother transition)
        
    Returns:
        Path to generated transition frame, or None if generation failed
    """
    if not image_generator or not os.path.exists(previous_frame_path):
        return None
    
    logger = logging.getLogger(__name__)
    
    try:
        transition_prompt = f"""Smooth visual transition between shots.
Previous shot ending, transitioning to: {current_shot_description[:300]}.
Style: {style}. Smooth camera movement, gradual visual change.
Maintain consistent lighting and color palette. No abrupt cuts.
Professional cinematic transition."""
        
        transition_output = await image_generator.generate_single_image(
            prompt=transition_prompt,
            reference_image_paths=[previous_frame_path],
            strength=strength,  # Lower strength for smoother blending
        )
        
        if transition_output:
            transition_output.save(output_path)
            logger.debug(f"Generated transition frame: {output_path}")
            return output_path
    except Exception as e:
        logger.warning(f"Failed to generate transition frame: {e}")
    
    return None


def composite_prop_on_image(
    background_path: str,
    prop_path: str,
    output_path: Optional[str] = None,
    position: str = "center",
    scale_factor: float = 0.15,
    vertical_position: str = "bottom",
    vertical_offset: float = 0.1,
    blend_mode: str = "normal",
    auto_remove_bg: bool = True,
) -> str:
    """
    Composite a prop reference image onto a background scene.
    
    This ensures props appear consistently across shots by overlaying
    the reference image rather than relying on AI generation.
    
    Args:
        background_path: Path to the background/scene image
        prop_path: Path to the prop reference image
        output_path: Output path (defaults to overwriting background)
        position: Horizontal position - "center", "left", "right", "center-left", "center-right"
        scale_factor: Prop size relative to image width (0.0-1.0, default 0.15)
        vertical_position: Vertical anchor - "bottom", "center", "top"
        vertical_offset: Offset from vertical anchor (0.0-1.0)
        blend_mode: Blending mode - "normal", "soft"
        auto_remove_bg: Automatically remove solid background from prop
    
    Returns:
        Path to the output image
    """
    if output_path is None:
        output_path = background_path
    
    if not os.path.exists(prop_path):
        logging.warning(f"Prop image not found: {prop_path}")
        return background_path
    
    try:
        # Open images
        background = Image.open(background_path).convert("RGBA")
        prop_img = Image.open(prop_path)
        
        # Auto-remove background from prop
        if auto_remove_bg:
            prop = _remove_solid_background(prop_img)
        else:
            prop = prop_img.convert("RGBA")
        
        bg_width, bg_height = background.size
        prop_width, prop_height = prop.size
        
        # Calculate prop size (scaled to scene width)
        target_width = int(bg_width * scale_factor)
        aspect_ratio = prop_height / prop_width
        target_height = int(target_width * aspect_ratio)
        
        # Don't let props get too tall
        max_height = int(bg_height * 0.4)
        if target_height > max_height:
            target_height = max_height
            target_width = int(target_height / aspect_ratio)
        
        # Resize prop
        prop = prop.resize((target_width, target_height), Image.Resampling.LANCZOS)
        
        # Calculate horizontal position
        if position == "center":
            x = (bg_width - target_width) // 2
        elif position == "left":
            x = int(bg_width * 0.1)
        elif position == "right":
            x = bg_width - target_width - int(bg_width * 0.1)
        elif position == "center-left":
            x = int(bg_width * 0.3) - target_width // 2
        elif position == "center-right":
            x = int(bg_width * 0.7) - target_width // 2
        else:
            x = (bg_width - target_width) // 2
        
        # Calculate vertical position
        if vertical_position == "bottom":
            y = bg_height - target_height - int(bg_height * vertical_offset)
        elif vertical_position == "top":
            y = int(bg_height * vertical_offset)
        elif vertical_position == "center":
            y = (bg_height - target_height) // 2 + int(bg_height * (vertical_offset - 0.5))
        else:
            y = bg_height - target_height - int(bg_height * vertical_offset)
        
        # Ensure prop stays within bounds
        x = max(0, min(x, bg_width - target_width))
        y = max(0, min(y, bg_height - target_height))
        
        # Apply soft edge blending if requested
        if blend_mode == "soft":
            prop = _apply_soft_edge(prop, edge_width=8)
        
        # Composite prop onto background
        background.paste(prop, (x, y), prop)
        
        # Convert to RGB and save
        final = background.convert("RGB")
        final.save(output_path)
        
        logging.info(f"Composited prop onto image: {output_path}")
        return output_path
        
    except Exception as e:
        logging.warning(f"Failed to composite prop: {e}")
        return background_path


def composite_multiple_props(
    background_path: str,
    prop_paths: List[str],
    output_path: Optional[str] = None,
    prop_positions: Optional[List[Tuple[str, str]]] = None,  # [(h_pos, v_pos), ...]
    scale_factors: Optional[List[float]] = None,
    auto_remove_bg: bool = True,
) -> str:
    """
    Composite multiple props onto a background scene.
    
    Args:
        background_path: Path to the background/scene image
        prop_paths: List of paths to prop reference images
        output_path: Output path (defaults to overwriting background)
        prop_positions: List of (horizontal, vertical) position tuples
        scale_factors: List of scale factors for each prop
        auto_remove_bg: Automatically remove solid backgrounds
    
    Returns:
        Path to the output image
    """
    if output_path is None:
        output_path = background_path
    
    if not prop_paths:
        return background_path
    
    # Default positions spread across the frame
    if prop_positions is None:
        if len(prop_paths) == 1:
            prop_positions = [("center", "bottom")]
        elif len(prop_paths) == 2:
            prop_positions = [("center-left", "bottom"), ("center-right", "bottom")]
        elif len(prop_paths) == 3:
            prop_positions = [("left", "bottom"), ("center", "bottom"), ("right", "bottom")]
        else:
            prop_positions = [("left", "bottom"), ("center-left", "bottom"), 
                           ("center-right", "bottom"), ("right", "bottom")][:len(prop_paths)]
    
    # Default scale factors (smaller than characters)
    if scale_factors is None:
        scale_factors = [0.12] * len(prop_paths)
    
    try:
        background = Image.open(background_path).convert("RGBA")
        bg_width, bg_height = background.size
        
        composited_count = 0
        
        for i, prop_path in enumerate(prop_paths):
            if not os.path.exists(prop_path):
                logging.warning(f"Prop not found: {prop_path}")
                continue
            
            # Load and process prop
            prop_img = Image.open(prop_path)
            if auto_remove_bg:
                prop = _remove_solid_background(prop_img)
            else:
                prop = prop_img.convert("RGBA")
            
            prop_width, prop_height = prop.size
            
            # Scale prop
            scale = scale_factors[i] if i < len(scale_factors) else 0.12
            target_width = int(bg_width * scale)
            aspect_ratio = prop_height / prop_width
            target_height = int(target_width * aspect_ratio)
            
            # Limit height
            max_height = int(bg_height * 0.35)
            if target_height > max_height:
                target_height = max_height
                target_width = int(target_height / aspect_ratio)
            
            prop = prop.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Get positions
            h_pos, v_pos = prop_positions[i] if i < len(prop_positions) else ("center", "bottom")
            
            # Calculate x position
            if h_pos == "center":
                x = (bg_width - target_width) // 2
            elif h_pos == "left":
                x = int(bg_width * 0.08)
            elif h_pos == "right":
                x = bg_width - target_width - int(bg_width * 0.08)
            elif h_pos == "center-left":
                x = int(bg_width * 0.28) - target_width // 2
            elif h_pos == "center-right":
                x = int(bg_width * 0.72) - target_width // 2
            else:
                x = (bg_width - target_width) // 2
            
            # Calculate y position
            if v_pos == "bottom":
                y = bg_height - target_height - int(bg_height * 0.08)
            elif v_pos == "top":
                y = int(bg_height * 0.08)
            elif v_pos == "center":
                y = (bg_height - target_height) // 2
            else:
                y = bg_height - target_height - int(bg_height * 0.1)
            
            # Ensure within bounds
            x = max(0, min(x, bg_width - target_width))
            y = max(0, min(y, bg_height - target_height))
            
            # Apply soft edge
            prop = _apply_soft_edge(prop, edge_width=6)
            
            # Composite
            background.paste(prop, (x, y), prop)
            composited_count += 1
        
        # Save result
        final = background.convert("RGB")
        final.save(output_path)
        
        logging.info(f"Composited {composited_count} props onto image: {output_path}")
        return output_path
        
    except Exception as e:
        logging.warning(f"Failed to composite multiple props: {e}")
        return background_path


def get_prop_position_from_description(
    description: str,
    prop_name: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Infer prop position from visual description.
    
    Args:
        description: Visual description of the shot/frame
        prop_name: Optional name of the specific prop
    
    Returns:
        Tuple of (horizontal_position, vertical_position)
    """
    desc_lower = description.lower()
    
    h_pos = "center"
    v_pos = "bottom"
    
    # Check for position keywords
    if prop_name:
        prop_lower = prop_name.lower()
        if prop_lower in desc_lower:
            idx = desc_lower.find(prop_lower)
            context = desc_lower[max(0, idx-40):min(len(desc_lower), idx+len(prop_lower)+40)]
            
            # Horizontal
            if any(kw in context for kw in ["left", "left side", "on the left"]):
                h_pos = "left"
            elif any(kw in context for kw in ["right", "right side", "on the right"]):
                h_pos = "right"
            
            # Vertical
            if any(kw in context for kw in ["above", "top", "upper", "sky", "floating"]):
                v_pos = "top"
            elif any(kw in context for kw in ["middle", "center", "mid"]):
                v_pos = "center"
    
    # Fallback to general keywords
    if h_pos == "center":
        if any(kw in desc_lower for kw in ["left side", "on the left", "to the left"]):
            h_pos = "left"
        elif any(kw in desc_lower for kw in ["right side", "on the right", "to the right"]):
            h_pos = "right"
    
    if v_pos == "bottom":
        if any(kw in desc_lower for kw in ["floating", "flying", "sky", "above", "top"]):
            v_pos = "top"
        elif any(kw in desc_lower for kw in ["middle", "hovering", "suspended"]):
            v_pos = "center"
    
    return h_pos, v_pos


def get_prop_scale_from_context(
    description: str,
    prop_name: Optional[str] = None,
    default_scale: float = 0.15,
) -> float:
    """
    Infer prop scale from context.
    
    Args:
        description: Visual description
        prop_name: Optional prop name
        default_scale: Default scale to use
    
    Returns:
        Scale factor (0.0-1.0)
    """
    desc_lower = description.lower()
    
    # Check for size keywords
    if any(kw in desc_lower for kw in ["large", "huge", "giant", "massive", "prominent"]):
        return 0.25
    elif any(kw in desc_lower for kw in ["small", "tiny", "little", "miniature"]):
        return 0.08
    elif any(kw in desc_lower for kw in ["close-up", "closeup", "detailed"]):
        return 0.3
    elif any(kw in desc_lower for kw in ["distant", "far away", "background"]):
        return 0.06
    
    return default_scale

