"""
ArtifactStore - Storage abstraction for artifacts.

Wraps ADK BaseArtifactService and provides:
- Save artifacts with automatic ID generation
- Load full content by ID (on-demand)
- List and query artifacts
- Version management

Key principle: LLM only sees artifact_id references, not full content.
"""

from typing import Optional
from datetime import datetime
import hashlib

from pydantic import BaseModel, Field

from .artifact import Artifact, ArtifactMetadata, ArtifactType


class ArtifactStore(BaseModel):
    """
    In-memory artifact store with optional ADK service backing.

    Stores artifacts by ID and provides retrieval by ID.
    LLM agents work with artifact IDs only; full content is loaded
    on-demand when needed for processing.
    """

    model_config = {"arbitrary_types_allowed": True}

    # Storage for artifact metadata
    _artifacts: dict[str, Artifact] = {}
    # Storage for full content (separate to keep Artifact lightweight)
    _contents: dict[str, str | bytes] = {}

    artifacts: dict[str, Artifact] = Field(
        default_factory=dict,
        description="Map of artifact_id to Artifact"
    )
    contents: dict[str, str | bytes] = Field(
        default_factory=dict,
        description="Map of artifact_id to full content"
    )

    def save(
        self,
        content: str | bytes,
        artifact_type: ArtifactType,
        filename: str,
        description: str,
        created_by_step_id: str,
        tags: Optional[list[str]] = None,
        preview_length: int = 500,
    ) -> str:
        """
        Save content and return artifact ID.

        Args:
            content: Full content to store
            artifact_type: Type of artifact
            filename: Suggested filename
            description: Human-readable description
            created_by_step_id: ID of step creating this artifact
            tags: Optional categorization tags
            preview_length: Max length for content preview

        Returns:
            artifact_id for referencing this artifact
        """
        artifact, full_content = Artifact.create(
            content=content,
            artifact_type=artifact_type,
            filename=filename,
            description=description,
            created_by_step_id=created_by_step_id,
            tags=tags,
            preview_length=preview_length,
        )

        artifact_id = artifact.metadata.artifact_id
        self.artifacts[artifact_id] = artifact
        self.contents[artifact_id] = full_content

        return artifact_id

    def load(self, artifact_id: str) -> Optional[str | bytes]:
        """
        Load full content by artifact ID.

        Args:
            artifact_id: ID of artifact to load

        Returns:
            Full content or None if not found
        """
        return self.contents.get(artifact_id)

    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        """
        Get artifact metadata by ID.

        Args:
            artifact_id: ID of artifact

        Returns:
            Artifact with metadata and preview, or None
        """
        return self.artifacts.get(artifact_id)

    def get_artifacts_by_step(self, step_id: str) -> list[Artifact]:
        """
        Get all artifacts created by a specific step.

        Args:
            step_id: ID of the step

        Returns:
            List of artifacts created by that step
        """
        return [
            a for a in self.artifacts.values()
            if a.metadata.created_by_step_id == step_id
        ]

    def get_artifacts_by_type(self, artifact_type: ArtifactType) -> list[Artifact]:
        """
        Get all artifacts of a specific type.

        Args:
            artifact_type: Type to filter by

        Returns:
            List of matching artifacts
        """
        return [
            a for a in self.artifacts.values()
            if a.metadata.artifact_type == artifact_type
        ]

    def get_artifacts_by_tag(self, tag: str) -> list[Artifact]:
        """
        Get all artifacts with a specific tag.

        Args:
            tag: Tag to filter by

        Returns:
            List of matching artifacts
        """
        return [
            a for a in self.artifacts.values()
            if tag in a.metadata.tags
        ]

    def list_artifacts(self) -> list[Artifact]:
        """
        List all stored artifacts.

        Returns:
            List of all artifacts
        """
        return list(self.artifacts.values())

    def update(
        self,
        artifact_id: str,
        content: str | bytes,
        description: Optional[str] = None,
    ) -> Optional[str]:
        """
        Update an existing artifact with new content.

        Creates a new version while maintaining the same artifact ID.

        Args:
            artifact_id: ID of artifact to update
            content: New content
            description: Optional new description

        Returns:
            artifact_id if successful, None if not found
        """
        existing = self.artifacts.get(artifact_id)
        if not existing:
            return None

        # Calculate new hash
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
            preview = content[:500]
        else:
            content_bytes = content
            preview = f"[Binary content: {len(content)} bytes]"

        content_hash = hashlib.sha256(content_bytes).hexdigest()

        # Update metadata
        new_metadata = existing.metadata.model_copy(
            update={
                "version": existing.metadata.version + 1,
                "updated_at": datetime.utcnow(),
                "size_bytes": len(content_bytes),
            }
        )
        if description:
            new_metadata = new_metadata.model_copy(update={"description": description})

        # Create updated artifact
        updated = Artifact(
            metadata=new_metadata,
            content_preview=preview,
            content_hash=content_hash,
        )

        self.artifacts[artifact_id] = updated
        self.contents[artifact_id] = content

        return artifact_id

    def delete(self, artifact_id: str) -> bool:
        """
        Delete an artifact.

        Args:
            artifact_id: ID of artifact to delete

        Returns:
            True if deleted, False if not found
        """
        if artifact_id in self.artifacts:
            del self.artifacts[artifact_id]
            del self.contents[artifact_id]
            return True
        return False

    def verify_content(self, artifact_id: str) -> bool:
        """
        Verify that stored content matches its hash.

        Args:
            artifact_id: ID of artifact to verify

        Returns:
            True if content hash matches, False otherwise
        """
        artifact = self.artifacts.get(artifact_id)
        content = self.contents.get(artifact_id)

        if not artifact or content is None:
            return False

        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        computed_hash = hashlib.sha256(content_bytes).hexdigest()
        return computed_hash == artifact.content_hash

    def get_context_summary(self, artifact_ids: Optional[list[str]] = None) -> str:
        """
        Generate a context summary for LLM consumption.

        Args:
            artifact_ids: Optional list of specific IDs, or all if None

        Returns:
            String summary of artifacts suitable for LLM context
        """
        if artifact_ids is None:
            artifacts = self.list_artifacts()
        else:
            artifacts = [
                self.artifacts[aid] for aid in artifact_ids
                if aid in self.artifacts
            ]

        if not artifacts:
            return "No artifacts available."

        lines = ["Available artifacts:"]
        for artifact in artifacts:
            lines.append(
                f"- [{artifact.metadata.artifact_id}] "
                f"{artifact.metadata.filename}: {artifact.metadata.description}"
            )

        return "\n".join(lines)
