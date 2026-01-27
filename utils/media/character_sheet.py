"""Character sheet splitting and extraction utilities.

This module provides functions to:
- Split a 3x3 character sheet grid into individual view images
- Extract specific view+expression combinations from a sheet
- Validate character sheet structure and dimensions
- Combine individual views into a character sheet grid
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from PIL import Image

from interfaces.entities.character_sheet import (
    CharacterView,
    CharacterExpression,
    CharacterViewData,
    CharacterViewSet,
    CharacterSheet,
    SHEET_COLUMNS,
    SHEET_ROWS,
    CELL_SIZE,
    SHEET_WIDTH,
    SHEET_HEIGHT,
)


logger = logging.getLogger(__name__)


class CharacterSheetSplitter:
    """Utility class for splitting character sheet grids into individual views."""
    
    def __init__(
        self,
        cell_size: int = CELL_SIZE,
        columns: List[CharacterView] = None,
        rows: List[CharacterExpression] = None,
    ):
        """Initialize the splitter with grid configuration.
        
        Args:
            cell_size: Size of each cell in pixels (default: 512)
            columns: List of views in column order (default: FRONT, SIDE, BACK)
            rows: List of expressions in row order (default: NEUTRAL, HAPPY, SAD)
        """
        self.cell_size = cell_size
        self.columns = columns or SHEET_COLUMNS
        self.rows = rows or SHEET_ROWS
        self.num_cols = len(self.columns)
        self.num_rows = len(self.rows)
    
    def get_cell_bounds(
        self,
        view: CharacterView,
        expression: CharacterExpression
    ) -> Tuple[int, int, int, int]:
        """Get the pixel bounds for a specific cell in the grid.
        
        Args:
            view: The column (FRONT, SIDE, BACK)
            expression: The row (NEUTRAL, HAPPY, SAD)
            
        Returns:
            Tuple of (left, upper, right, lower) pixel coordinates
        """
        col_idx = self.columns.index(view)
        row_idx = self.rows.index(expression)
        
        left = col_idx * self.cell_size
        upper = row_idx * self.cell_size
        right = left + self.cell_size
        lower = upper + self.cell_size
        
        return (left, upper, right, lower)
    
    def validate_sheet(self, sheet_path: str) -> Tuple[bool, str]:
        """Validate that an image is a valid character sheet.
        
        Args:
            sheet_path: Path to the character sheet image
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not os.path.exists(sheet_path):
            return False, f"Sheet file not found: {sheet_path}"
        
        try:
            with Image.open(sheet_path) as img:
                expected_width = self.cell_size * self.num_cols
                expected_height = self.cell_size * self.num_rows
                
                width, height = img.size
                
                # Allow some tolerance (±10%)
                width_ok = abs(width - expected_width) < expected_width * 0.1
                height_ok = abs(height - expected_height) < expected_height * 0.1
                
                if not width_ok or not height_ok:
                    return False, (
                        f"Sheet dimensions {width}x{height} don't match expected "
                        f"{expected_width}x{expected_height} (±10%)"
                    )
                
                return True, ""
                
        except Exception as e:
            return False, f"Failed to open sheet: {e}"
    
    def extract_view(
        self,
        sheet_path: str,
        view: CharacterView,
        expression: CharacterExpression,
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """Extract a single view from the character sheet.
        
        Args:
            sheet_path: Path to the character sheet image
            view: The view to extract (FRONT, SIDE, BACK)
            expression: The expression to extract (NEUTRAL, HAPPY, SAD)
            output_path: Optional output path; if None, generates one
            
        Returns:
            Path to the extracted view image, or None on failure
        """
        try:
            with Image.open(sheet_path) as sheet:
                # Scale bounds if sheet is not exactly the expected size
                scale_x = sheet.width / (self.cell_size * self.num_cols)
                scale_y = sheet.height / (self.cell_size * self.num_rows)
                
                col_idx = self.columns.index(view)
                row_idx = self.rows.index(expression)
                
                left = int(col_idx * self.cell_size * scale_x)
                upper = int(row_idx * self.cell_size * scale_y)
                right = int((col_idx + 1) * self.cell_size * scale_x)
                lower = int((row_idx + 1) * self.cell_size * scale_y)
                
                cell = sheet.crop((left, upper, right, lower))
                
                # Resize to standard cell size if needed
                if cell.size != (self.cell_size, self.cell_size):
                    cell = cell.resize(
                        (self.cell_size, self.cell_size),
                        Image.Resampling.LANCZOS
                    )
                
                # Generate output path if not provided
                if output_path is None:
                    sheet_dir = os.path.dirname(sheet_path)
                    output_path = os.path.join(
                        sheet_dir,
                        f"{view.value}_{expression.value}.png"
                    )
                
                # Ensure output directory exists
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                # Save as PNG with transparency support
                cell.save(output_path, "PNG")
                logger.info(f"Extracted {view.value}_{expression.value} to {output_path}")
                
                return output_path
                
        except Exception as e:
            logger.error(f"Failed to extract view from sheet: {e}")
            return None
    
    def split_sheet(
        self,
        sheet_path: str,
        output_dir: str,
        character_id: str = "character",
    ) -> Optional[CharacterSheet]:
        """Split a character sheet into all individual view images.
        
        Args:
            sheet_path: Path to the character sheet image
            output_dir: Directory to save extracted views
            character_id: ID for the character (used in CharacterSheet)
            
        Returns:
            CharacterSheet object with all extracted views, or None on failure
        """
        # Validate sheet first
        is_valid, error = self.validate_sheet(sheet_path)
        if not is_valid:
            logger.error(f"Invalid character sheet: {error}")
            return None
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Create character sheet object
        sheet = CharacterSheet(character_id=character_id)
        
        # Add the original sheet
        sheet.sheet = CharacterViewData(
            path=sheet_path,
            description="Full character sheet grid (3x3)"
        )
        
        # Extract all views
        view_sets = {}
        
        for view in self.columns:
            expressions = {}
            
            for expression in self.rows:
                output_path = os.path.join(
                    output_dir,
                    f"{view.value}_{expression.value}.png"
                )
                
                extracted_path = self.extract_view(
                    sheet_path,
                    view,
                    expression,
                    output_path
                )
                
                if extracted_path:
                    expressions[expression.value] = CharacterViewData(
                        path=extracted_path,
                        description=f"{view.value.title()} view, {expression.value} expression"
                    )
            
            if expressions:
                view_sets[view.value] = CharacterViewSet(
                    neutral=expressions.get("neutral"),
                    happy=expressions.get("happy"),
                    sad=expressions.get("sad"),
                )
        
        # Assign view sets to sheet
        sheet.front = view_sets.get("front")
        sheet.side = view_sets.get("side")
        sheet.back = view_sets.get("back")
        
        logger.info(f"Split character sheet into {output_dir}")
        return sheet
    
    def get_view_from_sheet(
        self,
        sheet_path: str,
        view: CharacterView = CharacterView.FRONT,
        expression: CharacterExpression = CharacterExpression.NEUTRAL,
    ) -> Optional[Image.Image]:
        """Get a specific view as a PIL Image without saving to disk.
        
        Args:
            sheet_path: Path to the character sheet image
            view: The view to extract
            expression: The expression to extract
            
        Returns:
            PIL Image object, or None on failure
        """
        try:
            with Image.open(sheet_path) as sheet:
                scale_x = sheet.width / (self.cell_size * self.num_cols)
                scale_y = sheet.height / (self.cell_size * self.num_rows)
                
                col_idx = self.columns.index(view)
                row_idx = self.rows.index(expression)
                
                left = int(col_idx * self.cell_size * scale_x)
                upper = int(row_idx * self.cell_size * scale_y)
                right = int((col_idx + 1) * self.cell_size * scale_x)
                lower = int((row_idx + 1) * self.cell_size * scale_y)
                
                cell = sheet.crop((left, upper, right, lower))
                
                # Resize to standard cell size if needed
                if cell.size != (self.cell_size, self.cell_size):
                    cell = cell.resize(
                        (self.cell_size, self.cell_size),
                        Image.Resampling.LANCZOS
                    )
                
                return cell.copy()
                
        except Exception as e:
            logger.error(f"Failed to get view from sheet: {e}")
            return None


def combine_views_to_sheet(
    views: Dict[Tuple[CharacterView, CharacterExpression], str],
    output_path: str,
    cell_size: int = CELL_SIZE,
) -> Optional[str]:
    """Combine individual view images into a character sheet grid.
    
    Args:
        views: Dictionary mapping (view, expression) tuples to image paths
        output_path: Path to save the combined sheet
        cell_size: Size of each cell in pixels
        
    Returns:
        Path to the combined sheet, or None on failure
    """
    try:
        num_cols = len(SHEET_COLUMNS)
        num_rows = len(SHEET_ROWS)
        
        # Create blank sheet
        sheet = Image.new(
            'RGBA',
            (cell_size * num_cols, cell_size * num_rows),
            (255, 255, 255, 255)
        )
        
        # Paste each view into the grid
        for (view, expression), path in views.items():
            if not os.path.exists(path):
                logger.warning(f"View image not found: {path}")
                continue
            
            col_idx = SHEET_COLUMNS.index(view)
            row_idx = SHEET_ROWS.index(expression)
            
            with Image.open(path) as img:
                # Resize to cell size if needed
                if img.size != (cell_size, cell_size):
                    img = img.resize(
                        (cell_size, cell_size),
                        Image.Resampling.LANCZOS
                    )
                
                # Convert to RGBA if needed
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                
                # Paste into sheet
                x = col_idx * cell_size
                y = row_idx * cell_size
                sheet.paste(img, (x, y))
        
        # Save the combined sheet
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        sheet.save(output_path, "PNG")
        logger.info(f"Combined views into sheet: {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Failed to combine views into sheet: {e}")
        return None


def extract_all_views_from_sheet(
    sheet_path: str,
    output_dir: str,
    character_id: str = "character",
) -> Optional[CharacterSheet]:
    """Convenience function to extract all views from a character sheet.
    
    Args:
        sheet_path: Path to the character sheet image
        output_dir: Directory to save extracted views
        character_id: ID for the character
        
    Returns:
        CharacterSheet object with all extracted views
    """
    splitter = CharacterSheetSplitter()
    return splitter.split_sheet(sheet_path, output_dir, character_id)


def get_single_view_from_sheet(
    sheet_path: str,
    view: CharacterView = CharacterView.FRONT,
    expression: CharacterExpression = CharacterExpression.NEUTRAL,
    output_path: Optional[str] = None,
) -> Optional[str]:
    """Convenience function to extract a single view from a sheet.
    
    Args:
        sheet_path: Path to the character sheet image
        view: The view to extract
        expression: The expression to extract
        output_path: Optional output path
        
    Returns:
        Path to the extracted view, or None on failure
    """
    splitter = CharacterSheetSplitter()
    return splitter.extract_view(sheet_path, view, expression, output_path)
