"""
Upload service providing unified interface for both tusd (local) and S3 multipart (production)
"""
import os
import requests
from typing import Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger

from .config import config, Environment
from .storage_manager import storage_manager


@dataclass
class UploadInfo:
    """Upload information for frontend"""
    method: str  # 'tus' or 's3_multipart'
    endpoint: str
    headers: Optional[Dict[str, str]] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class MultipartUploadResponse:
    """Response for S3 multipart upload initiation"""
    upload_id: str
    key: str
    presigned_urls: list
    complete_url: str
    abort_url: str


class UploadService:
    """Unified upload service supporting both tusd and S3 multipart uploads"""
    
    def __init__(self):
        self.config = config
        self.storage = storage_manager
        logger.info(f"Upload service initialized for {self.config.environment.value} environment")
    
    def get_upload_info(self) -> UploadInfo:
        """Get upload configuration for frontend based on environment"""
        
        if self.config.environment == Environment.LOCAL:
            return self._get_tus_upload_info()
        else:
            return self._get_s3_upload_info()
    
    def _get_tus_upload_info(self) -> UploadInfo:
        """Get tusd upload configuration for local development"""
        
        endpoint = self.config.tusd_url
        if not endpoint.endswith('/files'):
            endpoint = endpoint.rstrip('/') + '/files'
        
        return UploadInfo(
            method='tus',
            endpoint=endpoint,
            headers={
                'Tus-Resumable': '1.0.0'
            },
            metadata={
                'max_size': 10 * 1024 * 1024 * 1024,  # 10GB
                'chunk_size': 1 * 1024 * 1024,  # 1MB for local
                'protocols': ['tus']
            }
        )
    
    def _get_s3_upload_info(self) -> UploadInfo:
        """Get S3 multipart upload configuration for production"""
        
        return UploadInfo(
            method='s3_multipart',
            endpoint='/api/uploads/s3/initiate',  # API endpoint to initiate multipart upload
            headers={
                'Content-Type': 'application/json'
            },
            metadata={
                'max_size': 100 * 1024 * 1024 * 1024,  # 100GB
                'chunk_size': self.config.storage.multipart_chunksize,
                'max_concurrent_uploads': self.config.storage.max_concurrency,
                'protocols': ['s3_multipart'],
                'transfer_acceleration': self.config.storage.use_transfer_acceleration
            }
        )
    
    def initiate_multipart_upload(
        self, 
        filename: str, 
        file_size: int, 
        content_type: str = None
    ) -> MultipartUploadResponse:
        """Initiate S3 multipart upload and return presigned URLs"""
        
        if self.config.environment == Environment.LOCAL:
            raise ValueError("Multipart upload not supported in local environment")
        
        # Generate unique key for the file
        key = self.storage.generate_upload_key(filename, "uploads")
        
        try:
            # Create multipart upload
            upload_id = self.storage.create_multipart_upload(key, content_type)
            
            # Generate presigned URLs for all parts
            upload_info = self.storage.generate_presigned_upload_parts(
                key, upload_id, file_size, content_type
            )
            
            logger.info(f"Initiated multipart upload for {filename} ({file_size} bytes) with {len(upload_info.presigned_urls)} parts")
            
            return MultipartUploadResponse(
                upload_id=upload_info.upload_id,
                key=upload_info.key,
                presigned_urls=upload_info.presigned_urls,
                complete_url=upload_info.complete_url,
                abort_url=upload_info.abort_url
            )
            
        except Exception as e:
            logger.error(f"Failed to initiate multipart upload for {filename}: {e}")
            raise
    
    def complete_multipart_upload(
        self, 
        key: str, 
        upload_id: str, 
        parts: list
    ) -> Dict[str, Any]:
        """Complete S3 multipart upload"""
        
        if self.config.environment == Environment.LOCAL:
            raise ValueError("Multipart upload not supported in local environment")
        
        try:
            etag = self.storage.complete_multipart_upload(key, upload_id, parts)
            
            # Get object information
            object_info = self.storage.get_object_info(key)
            
            logger.info(f"Completed multipart upload for {key}")
            
            return {
                'key': key,
                'etag': etag,
                'size': object_info.get('size'),
                'location': f"s3://{self.config.storage.raw_bucket}/{key}",
                'url': f"s3://{self.config.storage.raw_bucket}/{key}"  # S3 URL for processing
            }
            
        except Exception as e:
            logger.error(f"Failed to complete multipart upload: {e}")
            raise
    
    def abort_multipart_upload(self, key: str, upload_id: str):
        """Abort S3 multipart upload"""
        
        if self.config.environment == Environment.LOCAL:
            raise ValueError("Multipart upload not supported in local environment")
        
        try:
            self.storage.abort_multipart_upload(key, upload_id)
            logger.info(f"Aborted multipart upload for {key}")
            
        except Exception as e:
            logger.error(f"Failed to abort multipart upload: {e}")
            raise
    
    def get_upload_progress(self, upload_id: str, key: str) -> Dict[str, Any]:
        """Get progress information for ongoing multipart upload"""
        
        if self.config.environment == Environment.LOCAL:
            # For tusd, we'd need to query the tusd server
            return self._get_tus_upload_progress(upload_id)
        else:
            # For S3, we can list multipart upload parts
            return self._get_s3_upload_progress(key, upload_id)
    
    def _get_tus_upload_progress(self, upload_id: str) -> Dict[str, Any]:
        """Get tusd upload progress"""
        
        try:
            response = requests.head(
                f"{self.config.tusd_internal_url}/files/{upload_id}",
                headers={'Tus-Resumable': '1.0.0'}
            )
            
            upload_offset = int(response.headers.get('Upload-Offset', 0))
            upload_length = int(response.headers.get('Upload-Length', 0))
            
            return {
                'upload_id': upload_id,
                'bytes_uploaded': upload_offset,
                'total_bytes': upload_length,
                'progress': (upload_offset / upload_length * 100) if upload_length > 0 else 0,
                'status': 'in_progress' if upload_offset < upload_length else 'completed'
            }
            
        except Exception as e:
            logger.error(f"Failed to get tusd upload progress: {e}")
            return {
                'upload_id': upload_id,
                'status': 'error',
                'error': str(e)
            }
    
    def _get_s3_upload_progress(self, key: str, upload_id: str) -> Dict[str, Any]:
        """Get S3 multipart upload progress"""
        
        try:
            # List uploaded parts
            response = self.storage.s3_client.list_parts(
                Bucket=self.config.storage.raw_bucket,
                Key=key,
                UploadId=upload_id
            )
            
            parts = response.get('Parts', [])
            total_uploaded = sum(part['Size'] for part in parts)
            
            return {
                'upload_id': upload_id,
                'key': key,
                'parts_uploaded': len(parts),
                'bytes_uploaded': total_uploaded,
                'status': 'in_progress'
            }
            
        except Exception as e:
            logger.error(f"Failed to get S3 upload progress: {e}")
            return {
                'upload_id': upload_id,
                'key': key,
                'status': 'error',
                'error': str(e)
            }


# Global upload service instance
upload_service = UploadService()