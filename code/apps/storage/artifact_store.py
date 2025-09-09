"""
ArtifactStore shim with facet-root canonicalization.

Thin wrapper over storage_service that enforces WorldPath conventions.
"""
import hashlib
from typing import Optional

from .service import storage_service
from apps.core.predicates.builtins import canon_path_facet_root


class ArtifactStore:
    """
    WorldPath-aware artifact storage with facet-root enforcement.
    
    Ensures all paths follow `/artifacts/...` or `/streams/...` convention
    and provides CID computation for content addressing.
    """
    
    def __init__(self):
        """Initialize artifact store."""
        self._service = storage_service
    
    def put_bytes(
        self, 
        world_path: str, 
        data: bytes, 
        content_type: str = 'application/octet-stream'
    ) -> str:
        """
        Store bytes at canonical WorldPath.
        
        Args:
            world_path: World path (e.g., '/artifacts/inputs/...')
            data: Bytes to store
            content_type: MIME content type
            
        Returns:
            Canonical world path where data was stored
            
        Raises:
            ValueError: If world_path is invalid
        """
        # Canonicalize and validate path
        canonical_path = canon_path_facet_root(world_path)
        
        # Store via storage service
        self._service.upload_bytes(
            data=data,
            key=canonical_path,
            content_type=content_type,
            bucket='default'
        )
        
        return canonical_path
    
    def get_bytes(self, world_path: str) -> Optional[bytes]:
        """
        Retrieve bytes from canonical WorldPath.
        
        Args:
            world_path: World path to retrieve
            
        Returns:
            Bytes data or None if not found
            
        Raises:
            ValueError: If world_path is invalid
        """
        # Canonicalize and validate path
        canonical_path = canon_path_facet_root(world_path)
        
        try:
            # Download via storage service
            file_obj = self._service.download_file(canonical_path, 'default')
            if hasattr(file_obj, 'read'):
                return file_obj.read()
            return file_obj
        except Exception:
            return None
    
    def presign(self, world_path: str, ttl_s: int = 3600) -> str:
        """
        Generate presigned URL for WorldPath.
        
        Args:
            world_path: World path to presign
            ttl_s: Time-to-live in seconds
            
        Returns:
            Presigned URL
            
        Raises:
            ValueError: If world_path is invalid
        """
        # Canonicalize and validate path
        canonical_path = canon_path_facet_root(world_path)
        
        # Generate presigned URL
        return self._service.get_file_url(
            key=canonical_path,
            bucket='default',
            expires_in=ttl_s
        )
    
    def exists(self, world_path: str) -> bool:
        """
        Check if artifact exists at WorldPath.
        
        Args:
            world_path: World path to check
            
        Returns:
            True if exists, False otherwise
        """
        try:
            canonical_path = canon_path_facet_root(world_path)
            return self._service.file_exists(canonical_path, 'default')
        except (ValueError, Exception):
            return False
    
    def compute_cid(self, data: bytes) -> str:
        """
        Compute content identifier for data.
        
        Args:
            data: Bytes to compute CID for
            
        Returns:
            Content identifier (BLAKE3 or SHA256 prefixed)
        """
        try:
            import blake3
            return 'b3:' + blake3.blake3(data).hexdigest()
        except ImportError:
            return 's256:' + hashlib.sha256(data).hexdigest()
    
    def put_file(
        self,
        world_path: str,
        file_path: str,
        content_type: Optional[str] = None
    ) -> str:
        """
        Store file at canonical WorldPath.
        
        Args:
            world_path: World path destination
            file_path: Local file path to upload
            content_type: Optional MIME type
            
        Returns:
            Canonical world path where file was stored
        """
        # Read file and store as bytes
        with open(file_path, 'rb') as f:
            data = f.read()
        
        # Guess content type if not provided
        if not content_type:
            import mimetypes
            content_type, _ = mimetypes.guess_type(file_path)
            if not content_type:
                content_type = 'application/octet-stream'
        
        return self.put_bytes(world_path, data, content_type)


# Singleton instance
artifact_store = ArtifactStore()