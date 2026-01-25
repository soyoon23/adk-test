"""
Artifact data models for storing agent outputs.

Artifacts represent any output produced by agent steps:
- Documents (markdown, text)
- Structured data (JSON, CSV)
- Code files
- Images
- Binary files
"""

from enum import Enum
from typing import Optional
from datetime import datetime
import hashlib
import uuid

from pydantic import BaseModel, Field


class ArtifactType(Enum):
    """Types of artifacts that can be produced by agent steps."""
    TEXT = "text"
    DOCUMENT = "document"
    JSON = "json"
    CSV = "csv"
    IMAGE = "image"
    CODE = "code"
    BINARY = "binary"


class ArtifactMetadata(BaseModel):
    """
    Metadata for an artifact.

    This is the lightweight representation passed to LLMs to avoid
    context explosion from large artifact contents.
    """
    artifact_id: str = Field(
        description="Unique identifier in 'art-xxxx' format"
    )
    artifact_type: ArtifactType = Field(
        description="Type of the artifact content"
    )
    filename: str = Field(
        description="Suggested filename for the artifact"
    )
    description: str = Field(
        description="Human-readable description of the artifact"
    )
    created_by_step_id: str = Field(
        description="ID of the step that created this artifact"
    )
    version: int = Field(
        default=1,
        description="Version number for artifact updates"
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for categorization and filtering"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when artifact was created"
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last update"
    )
    mime_type: Optional[str] = Field(
        default=None,
        description="MIME type of the content"
    )
    size_bytes: Optional[int] = Field(
        default=None,
        description="Size of content in bytes"
    )

    @classmethod
    def generate_id(cls) -> str:
        """Generate a new artifact ID."""
        return f"art-{uuid.uuid4().hex[:12]}"


class Artifact(BaseModel):
    """
    Complete artifact with metadata and content preview.

    The full content is stored separately in ArtifactStore.
    Only content_preview is included here to prevent context explosion.
    """
    metadata: ArtifactMetadata = Field(
        description="Artifact metadata"
    )
    content_preview: str = Field(
        default="",
        description="Preview of content (first N characters) for context"
    )
    content_hash: str = Field(
        description="SHA-256 hash of full content for verification"
    )

    @classmethod
    def create(
        cls,
        content: str | bytes,
        artifact_type: ArtifactType,
        filename: str,
        description: str,
        created_by_step_id: str,
        tags: Optional[list[str]] = None,
        preview_length: int = 500,
    ) -> tuple["Artifact", str | bytes]:
        """
        Create an artifact from content.

        Args:
            content: The full content (string or bytes)
            artifact_type: Type of artifact
            filename: Suggested filename
            description: Human-readable description
            created_by_step_id: ID of creating step
            tags: Optional tags
            preview_length: Maximum length of content preview

        Returns:
            Tuple of (Artifact, full_content) - caller should store full_content
        """
        # Calculate hash
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
            content_preview = content[:preview_length]
        else:
            content_bytes = content
            content_preview = f"[Binary content: {len(content)} bytes]"

        content_hash = hashlib.sha256(content_bytes).hexdigest()

        # Determine MIME type
        mime_type = cls._get_mime_type(artifact_type, filename)

        metadata = ArtifactMetadata(
            artifact_id=ArtifactMetadata.generate_id(),
            artifact_type=artifact_type,
            filename=filename,
            description=description,
            created_by_step_id=created_by_step_id,
            tags=tags or [],
            mime_type=mime_type,
            size_bytes=len(content_bytes),
        )

        artifact = cls(
            metadata=metadata,
            content_preview=content_preview,
            content_hash=content_hash,
        )

        return artifact, content

    @staticmethod
    def _get_mime_type(artifact_type: ArtifactType, filename: str) -> str:
        """Determine MIME type from artifact type and filename."""
        type_map = {
            ArtifactType.TEXT: "text/plain",
            ArtifactType.DOCUMENT: "text/markdown",
            ArtifactType.JSON: "application/json",
            ArtifactType.CSV: "text/csv",
            ArtifactType.IMAGE: "image/png",
            ArtifactType.CODE: "text/plain",
            ArtifactType.BINARY: "application/octet-stream",
        }

        # Refine based on file extension
        ext = filename.lower().split(".")[-1] if "." in filename else ""
        ext_map = {
            "md": "text/markdown",
            "html": "text/html",
            "py": "text/x-python",
            "js": "text/javascript",
            "ts": "text/typescript",
            "json": "application/json",
            "csv": "text/csv",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "svg": "image/svg+xml",
        }

        return ext_map.get(ext, type_map.get(artifact_type, "application/octet-stream"))

    def to_context_string(self) -> str:
        """
        Generate a string representation suitable for LLM context.

        Returns only essential info to prevent context explosion.
        """
        return (
            f"[Artifact: {self.metadata.artifact_id}]\n"
            f"Type: {self.metadata.artifact_type.value}\n"
            f"File: {self.metadata.filename}\n"
            f"Description: {self.metadata.description}\n"
            f"Preview:\n{self.content_preview}"
        )
