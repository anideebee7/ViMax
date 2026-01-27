"""Checkpoint system for pipeline resume functionality.

This module provides utilities to track pipeline progress and enable seamless
resume from any point, handling incomplete, aborted, or errored runs.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class RunStatus(Enum):
    """Status of a pipeline run."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"
    PARTIAL = "partial"  # Some phases completed, some not


@dataclass
class PhaseCheckpoint:
    """Checkpoint for a single phase of pipeline execution."""
    phase_name: str
    status: str  # "not_started", "in_progress", "completed", "failed"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    output_files: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "PhaseCheckpoint":
        return cls(**data)


@dataclass
class EpisodeCheckpoint:
    """Checkpoint for a single episode in a series pipeline."""
    episode_number: int
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    output_files: List[str] = field(default_factory=list)
    phases: Dict[str, PhaseCheckpoint] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "episode_number": self.episode_number,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "output_files": self.output_files,
            "phases": {k: v.to_dict() for k, v in self.phases.items()},
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "EpisodeCheckpoint":
        phases = {
            k: PhaseCheckpoint.from_dict(v) 
            for k, v in data.get("phases", {}).items()
        }
        return cls(
            episode_number=data["episode_number"],
            status=data["status"],
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
            output_files=data.get("output_files", []),
            phases=phases,
        )


@dataclass
class SceneCheckpoint:
    """Checkpoint for a single scene in a movie/series pipeline."""
    scene_number: int
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    output_files: List[str] = field(default_factory=list)
    shots: Dict[int, "ShotCheckpoint"] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "scene_number": self.scene_number,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "output_files": self.output_files,
            "shots": {str(k): v.to_dict() for k, v in self.shots.items()},
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "SceneCheckpoint":
        shots = {
            int(k): ShotCheckpoint.from_dict(v)
            for k, v in data.get("shots", {}).items()
        }
        return cls(
            scene_number=data["scene_number"],
            status=data["status"],
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            error=data.get("error"),
            output_files=data.get("output_files", []),
            shots=shots,
        )


@dataclass
class ShotCheckpoint:
    """Checkpoint for a single shot/frame in a pipeline."""
    shot_number: int
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    image_path: Optional[str] = None
    video_path: Optional[str] = None
    raw_image_path: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ShotCheckpoint":
        return cls(**data)


@dataclass
class RunCheckpoint:
    """Complete checkpoint for a pipeline run."""
    run_id: str
    pipeline_type: str
    status: str  # RunStatus value
    created_at: str
    updated_at: str
    phases: Dict[str, PhaseCheckpoint] = field(default_factory=dict)
    episodes: Dict[int, EpisodeCheckpoint] = field(default_factory=dict)
    scenes: Dict[int, SceneCheckpoint] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "run_id": self.run_id,
            "pipeline_type": self.pipeline_type,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "phases": {k: v.to_dict() for k, v in self.phases.items()},
            "episodes": {k: v.to_dict() for k, v in self.episodes.items()},
            "scenes": {k: v.to_dict() for k, v in self.scenes.items()},
            "errors": self.errors,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "RunCheckpoint":
        phases = {
            k: PhaseCheckpoint.from_dict(v)
            for k, v in data.get("phases", {}).items()
        }
        episodes = {
            int(k): EpisodeCheckpoint.from_dict(v)
            for k, v in data.get("episodes", {}).items()
        }
        scenes = {
            int(k): SceneCheckpoint.from_dict(v)
            for k, v in data.get("scenes", {}).items()
        }
        return cls(
            run_id=data["run_id"],
            pipeline_type=data["pipeline_type"],
            status=data["status"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            phases=phases,
            episodes=episodes,
            scenes=scenes,
            errors=data.get("errors", []),
            metadata=data.get("metadata", {}),
        )


class CheckpointManager:
    """Manages checkpoint state for pipeline runs."""
    
    def __init__(self, working_dir: str, run_id: str, pipeline_type: str):
        """Initialize checkpoint manager.
        
        Args:
            working_dir: Working directory for the run
            run_id: Unique run identifier
            pipeline_type: Type of pipeline (e.g., "learning_series", "movie")
        """
        self.working_dir = working_dir
        self.run_id = run_id
        self.pipeline_type = pipeline_type
        self.checkpoint_path = os.path.join(working_dir, "checkpoint.json")
        self._checkpoint: Optional[RunCheckpoint] = None
    
    def load(self) -> Optional[RunCheckpoint]:
        """Load checkpoint from disk."""
        if self._checkpoint:
            return self._checkpoint
        
        if not os.path.exists(self.checkpoint_path):
            logger.debug(f"No checkpoint file found at {self.checkpoint_path}")
            return None
        
        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._checkpoint = RunCheckpoint.from_dict(data)
            logger.info(f"Loaded checkpoint: {self._checkpoint.status}")
            return self._checkpoint
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            return None
    
    def save(self):
        """Save checkpoint to disk."""
        if not self._checkpoint:
            return
        
        self._checkpoint.updated_at = datetime.utcnow().isoformat()
        os.makedirs(os.path.dirname(self.checkpoint_path), exist_ok=True)
        
        try:
            with open(self.checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(self._checkpoint.to_dict(), f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved checkpoint to {self.checkpoint_path}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
    
    def initialize(self, metadata: Optional[Dict[str, Any]] = None):
        """Initialize a new checkpoint."""
        self._checkpoint = RunCheckpoint(
            run_id=self.run_id,
            pipeline_type=self.pipeline_type,
            status=RunStatus.NOT_STARTED.value,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
            metadata=metadata or {},
        )
        self.save()
    
    def start_phase(self, phase_name: str, metadata: Optional[Dict[str, Any]] = None):
        """Mark a phase as started."""
        if not self._checkpoint:
            self.initialize()
        
        self._checkpoint.status = RunStatus.IN_PROGRESS.value
        self._checkpoint.phases[phase_name] = PhaseCheckpoint(
            phase_name=phase_name,
            status="in_progress",
            started_at=datetime.utcnow().isoformat(),
            metadata=metadata or {},
        )
        self.save()
    
    def complete_phase(self, phase_name: str, output_files: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None):
        """Mark a phase as completed."""
        if not self._checkpoint:
            return
        
        if phase_name not in self._checkpoint.phases:
            self.start_phase(phase_name, metadata)
        
        phase = self._checkpoint.phases[phase_name]
        phase.status = "completed"
        phase.completed_at = datetime.utcnow().isoformat()
        if output_files:
            phase.output_files = output_files
        if metadata:
            phase.metadata.update(metadata)
        self.save()
    
    def fail_phase(self, phase_name: str, error: str):
        """Mark a phase as failed."""
        if not self._checkpoint:
            return
        
        if phase_name not in self._checkpoint.phases:
            self.start_phase(phase_name)
        
        phase = self._checkpoint.phases[phase_name]
        phase.status = "failed"
        phase.error = error
        phase.completed_at = datetime.utcnow().isoformat()
        self._checkpoint.errors.append(f"{phase_name}: {error}")
        self._checkpoint.status = RunStatus.FAILED.value
        self.save()
    
    def start_episode(self, episode_number: int, metadata: Optional[Dict[str, Any]] = None):
        """Mark an episode as started."""
        if not self._checkpoint:
            self.initialize()
        
        self._checkpoint.status = RunStatus.IN_PROGRESS.value
        self._checkpoint.episodes[episode_number] = EpisodeCheckpoint(
            episode_number=episode_number,
            status="in_progress",
            started_at=datetime.utcnow().isoformat(),
        )
        self.save()
    
    def complete_episode(self, episode_number: int, output_files: Optional[List[str]] = None):
        """Mark an episode as completed."""
        if not self._checkpoint:
            return
        
        if episode_number not in self._checkpoint.episodes:
            self.start_episode(episode_number)
        
        episode = self._checkpoint.episodes[episode_number]
        episode.status = "completed"
        episode.completed_at = datetime.utcnow().isoformat()
        if output_files:
            episode.output_files = output_files
        self.save()
    
    def fail_episode(self, episode_number: int, error: str):
        """Mark an episode as failed."""
        if not self._checkpoint:
            return
        
        if episode_number not in self._checkpoint.episodes:
            self.start_episode(episode_number)
        
        episode = self._checkpoint.episodes[episode_number]
        episode.status = "failed"
        episode.error = error
        episode.completed_at = datetime.utcnow().isoformat()
        self._checkpoint.errors.append(f"Episode {episode_number}: {error}")
        self._checkpoint.status = RunStatus.PARTIAL.value
        self.save()
    
    def start_scene(self, scene_number: int):
        """Mark a scene as started."""
        if not self._checkpoint:
            self.initialize()
        
        self._checkpoint.status = RunStatus.IN_PROGRESS.value
        self._checkpoint.scenes[scene_number] = SceneCheckpoint(
            scene_number=scene_number,
            status="in_progress",
            started_at=datetime.utcnow().isoformat(),
        )
        self.save()
    
    def complete_scene(self, scene_number: int, output_files: Optional[List[str]] = None):
        """Mark a scene as completed."""
        if not self._checkpoint:
            return
        
        if scene_number not in self._checkpoint.scenes:
            self.start_scene(scene_number)
        
        scene = self._checkpoint.scenes[scene_number]
        scene.status = "completed"
        scene.completed_at = datetime.utcnow().isoformat()
        if output_files:
            scene.output_files = output_files
        self.save()
    
    def fail_scene(self, scene_number: int, error: str):
        """Mark a scene as failed."""
        if not self._checkpoint:
            return
        
        if scene_number not in self._checkpoint.scenes:
            self.start_scene(scene_number)
        
        scene = self._checkpoint.scenes[scene_number]
        scene.status = "failed"
        scene.error = error
        scene.completed_at = datetime.utcnow().isoformat()
        self._checkpoint.errors.append(f"Scene {scene_number}: {error}")
        self._checkpoint.status = RunStatus.PARTIAL.value
        self.save()
    
    def mark_completed(self):
        """Mark the entire run as completed."""
        if not self._checkpoint:
            return
        
        self._checkpoint.status = RunStatus.COMPLETED.value
        self._checkpoint.updated_at = datetime.utcnow().isoformat()
        self.save()
    
    def mark_aborted(self):
        """Mark the run as aborted."""
        if not self._checkpoint:
            return
        
        self._checkpoint.status = RunStatus.ABORTED.value
        self._checkpoint.updated_at = datetime.utcnow().isoformat()
        self.save()
    
    def get_completed_phases(self) -> Set[str]:
        """Get set of completed phase names."""
        if not self._checkpoint:
            return set()
        return {
            name for name, phase in self._checkpoint.phases.items()
            if phase.status == "completed"
        }
    
    def get_completed_episodes(self) -> Set[int]:
        """Get set of completed episode numbers."""
        if not self._checkpoint:
            return set()
        return {
            num for num, episode in self._checkpoint.episodes.items()
            if episode.status == "completed"
        }
    
    def get_completed_scenes(self) -> Set[int]:
        """Get set of completed scene numbers."""
        if not self._checkpoint:
            return set()
        return {
            num for num, scene in self._checkpoint.scenes.items()
            if scene.status == "completed"
        }
    
    def is_phase_completed(self, phase_name: str) -> bool:
        """Check if a phase is completed."""
        return phase_name in self.get_completed_phases()
    
    def is_episode_completed(self, episode_number: int) -> bool:
        """Check if an episode is completed."""
        return episode_number in self.get_completed_episodes()
    
    def is_scene_completed(self, scene_number: int) -> bool:
        """Check if a scene is completed."""
        return scene_number in self.get_completed_scenes()
    
    def start_shot(self, scene_number: int, shot_number: int):
        """Mark a shot as started."""
        if not self._checkpoint:
            self.initialize()
        
        if scene_number not in self._checkpoint.scenes:
            self.start_scene(scene_number)
        
        scene = self._checkpoint.scenes[scene_number]
        scene.shots[shot_number] = ShotCheckpoint(
            shot_number=shot_number,
            status="in_progress",
            started_at=datetime.utcnow().isoformat(),
        )
        self.save()
    
    def complete_shot(
        self,
        scene_number: int,
        shot_number: int,
        image_path: Optional[str] = None,
        video_path: Optional[str] = None,
        raw_image_path: Optional[str] = None,
    ):
        """Mark a shot as completed."""
        if not self._checkpoint:
            return
        
        if scene_number not in self._checkpoint.scenes:
            self.start_scene(scene_number)
        
        scene = self._checkpoint.scenes[scene_number]
        if shot_number not in scene.shots:
            self.start_shot(scene_number, shot_number)
        
        shot = scene.shots[shot_number]
        shot.status = "completed"
        shot.completed_at = datetime.utcnow().isoformat()
        shot.image_path = image_path
        shot.video_path = video_path
        shot.raw_image_path = raw_image_path
        self.save()
    
    def fail_shot(self, scene_number: int, shot_number: int, error: str):
        """Mark a shot as failed."""
        if not self._checkpoint:
            return
        
        if scene_number not in self._checkpoint.scenes:
            self.start_scene(scene_number)
        
        scene = self._checkpoint.scenes[scene_number]
        if shot_number not in scene.shots:
            self.start_shot(scene_number, shot_number)
        
        shot = scene.shots[shot_number]
        shot.status = "failed"
        shot.error = error
        shot.completed_at = datetime.utcnow().isoformat()
        self._checkpoint.errors.append(f"Scene {scene_number} Shot {shot_number}: {error}")
        self._checkpoint.status = RunStatus.PARTIAL.value
        self.save()
    
    def is_shot_completed(self, scene_number: int, shot_number: int) -> bool:
        """Check if a shot is completed."""
        if not self._checkpoint:
            return False
        
        scene = self._checkpoint.scenes.get(scene_number)
        if not scene:
            return False
        
        shot = scene.shots.get(shot_number)
        return shot is not None and shot.status == "completed"
    
    def get_shot_checkpoint(self, scene_number: int, shot_number: int) -> Optional[ShotCheckpoint]:
        """Get checkpoint for a specific shot."""
        if not self._checkpoint:
            return None
        
        scene = self._checkpoint.scenes.get(scene_number)
        if not scene:
            return None
        
        return scene.shots.get(shot_number)
    
    def can_resume(self) -> bool:
        """Check if run can be resumed (has checkpoint and is not completed)."""
        checkpoint = self.load()
        if not checkpoint:
            return False
        
        return checkpoint.status in [
            RunStatus.IN_PROGRESS.value,
            RunStatus.PARTIAL.value,
            RunStatus.FAILED.value,
            RunStatus.ABORTED.value,
        ]
    
    def get_resume_info(self) -> Dict[str, Any]:
        """Get information about what can be resumed."""
        checkpoint = self.load()
        if not checkpoint:
            return {"can_resume": False, "status": "no_checkpoint"}
        
        return {
            "can_resume": self.can_resume(),
            "status": checkpoint.status,
            "completed_phases": list(self.get_completed_phases()),
            "completed_episodes": list(self.get_completed_episodes()),
            "completed_scenes": list(self.get_completed_scenes()),
            "errors": checkpoint.errors,
            "created_at": checkpoint.created_at,
            "updated_at": checkpoint.updated_at,
        }
