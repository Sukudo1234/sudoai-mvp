"""
Enhanced storage manager supporting both MinIO (local) and S3 (production)
with multipart upload capabilities and environment-aware operations
"""
import os
import boto3
import hashlib
import uuid
from typing import Dict, List, Optional, Tuple, Union
from botocore.client import Config
from botocore.exceptions import ClientError
from dataclasses import dataclass
from loguru import logger

from .config import config, Environment


@dataclass
class MultipartUpload:
    """Multipart upload session information"""
    upload_id: str
    key: str
    parts: List[Dict]
    bucket: str


@dataclass
class PresignedUploadInfo:
    """Information for presigned multipart uploads"""
    upload_id: str
    key: str
    presigned_urls: List[Dict]  # [{"part_number": 1, "url": "..."}]
    complete_url: str
    abort_url: str


class StorageManager:
    """Environment-aware storage manager for S3/MinIO operations"""
    
    def __init__(self):
        self.config = config.storage
        self.environment = config.environment
        
        # Initialize S3 client based on environment
        self.s3_client = self._create_s3_client()
        
        # Ensure buckets exist
        self._ensure_buckets()
        
        logger.info(f"Storage manager initialized for {self.environment.value} environment")
    
    def _create_s3_client(self) -> boto3.client:
        """Create S3 client configured for current environment"""
        
        client_config = Config(
            signature_version='s3v4',
            s3={
                'addressing_style': 'path' if self.environment == Environment.LOCAL else 'virtual'
            },
            retries={'max_attempts': 3, 'mode': 'adaptive'}
        )
        
        # Add transfer acceleration for production
        if self.environment == Environment.PRODUCTION and self.config.use_transfer_acceleration:
            client_config.s3['use_accelerate_endpoint'] = True
        
        return boto3.client(
            's3',
            endpoint_url=self.config.endpoint_url,
            aws_access_key_id=self.config.access_key,
            aws_secret_access_key=self.config.secret_key,
            region_name=self.config.region,
            use_ssl=self.config.use_ssl,
            config=client_config
        )
    
    def _ensure_buckets(self):
        """Ensure required buckets exist"""
        for bucket in [self.config.raw_bucket, self.config.out_bucket]:
            try:
                self.s3_client.head_bucket(Bucket=bucket)
                logger.debug(f"Bucket {bucket} exists")
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.info(f"Creating bucket {bucket}")
                    self._create_bucket(bucket)
                else:
                    logger.error(f"Error checking bucket {bucket}: {e}")
                    raise
    
    def _create_bucket(self, bucket_name: str):
        """Create bucket with appropriate configuration for environment"""
        try:
            if self.config.region == 'us-east-1':
                # us-east-1 doesn't need LocationConstraint
                self.s3_client.create_bucket(Bucket=bucket_name)
            else:
                self.s3_client.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': self.config.region}
                )
            logger.info(f"Created bucket {bucket_name}")
        except ClientError as e:
            if e.response['Error']['Code'] != 'BucketAlreadyExists':
                logger.error(f"Failed to create bucket {bucket_name}: {e}")
                raise
    
    def generate_upload_key(self, filename: str, prefix: str = "uploads") -> str:
        """Generate a unique key for uploaded files"""
        file_id = str(uuid.uuid4())
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        return f"{prefix}/{file_id[:8]}/{safe_filename}"
    
    def create_multipart_upload(self, key: str, content_type: str = None) -> str:
        """Create a multipart upload and return upload_id"""
        
        params = {
            'Bucket': self.config.raw_bucket,
            'Key': key
        }
        
        if content_type:
            params['ContentType'] = content_type
            
        # Add server-side encryption for production
        if self.environment == Environment.PRODUCTION:
            params['ServerSideEncryption'] = 'AES256'
        
        try:
            response = self.s3_client.create_multipart_upload(**params)
            upload_id = response['UploadId']
            logger.info(f"Created multipart upload {upload_id} for key {key}")
            return upload_id
            
        except ClientError as e:
            logger.error(f"Failed to create multipart upload for {key}: {e}")
            raise
    
    def generate_presigned_upload_parts(
        self, 
        key: str, 
        upload_id: str, 
        file_size: int,
        content_type: str = None
    ) -> PresignedUploadInfo:
        """Generate presigned URLs for multipart upload parts"""
        
        # Calculate number of parts
        part_size = self.config.multipart_chunksize
        num_parts = (file_size + part_size - 1) // part_size
        
        logger.info(f"Generating {num_parts} presigned URLs for {key} (size: {file_size})")
        
        presigned_urls = []
        
        for part_number in range(1, num_parts + 1):
            try:
                # Calculate part size for this part (last part might be smaller)
                current_part_size = min(part_size, file_size - (part_number - 1) * part_size)
                
                url = self.s3_client.generate_presigned_url(
                    'upload_part',
                    Params={
                        'Bucket': self.config.raw_bucket,
                        'Key': key,
                        'UploadId': upload_id,
                        'PartNumber': part_number
                    },
                    ExpiresIn=3600  # 1 hour
                )
                
                presigned_urls.append({
                    'part_number': part_number,
                    'url': url,
                    'size': current_part_size
                })
                
            except ClientError as e:
                logger.error(f"Failed to generate presigned URL for part {part_number}: {e}")
                raise
        
        # Generate URLs for complete and abort operations
        complete_url = self.s3_client.generate_presigned_url(
            'complete_multipart_upload',
            Params={
                'Bucket': self.config.raw_bucket,
                'Key': key,
                'UploadId': upload_id
            },
            ExpiresIn=3600
        )
        
        abort_url = self.s3_client.generate_presigned_url(
            'abort_multipart_upload',
            Params={
                'Bucket': self.config.raw_bucket,
                'Key': key,
                'UploadId': upload_id
            },
            ExpiresIn=3600
        )
        
        return PresignedUploadInfo(
            upload_id=upload_id,
            key=key,
            presigned_urls=presigned_urls,
            complete_url=complete_url,
            abort_url=abort_url
        )
    
    def complete_multipart_upload(self, key: str, upload_id: str, parts: List[Dict]) -> str:
        """Complete multipart upload with part information"""
        
        try:
            response = self.s3_client.complete_multipart_upload(
                Bucket=self.config.raw_bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )
            
            logger.info(f"Completed multipart upload {upload_id} for key {key}")
            return response['ETag']
            
        except ClientError as e:
            logger.error(f"Failed to complete multipart upload {upload_id}: {e}")
            raise
    
    def abort_multipart_upload(self, key: str, upload_id: str):
        """Abort multipart upload"""
        
        try:
            self.s3_client.abort_multipart_upload(
                Bucket=self.config.raw_bucket,
                Key=key,
                UploadId=upload_id
            )
            logger.info(f"Aborted multipart upload {upload_id} for key {key}")
            
        except ClientError as e:
            logger.error(f"Failed to abort multipart upload {upload_id}: {e}")
            raise
    
    def upload_file(self, local_path: str, key: str, bucket: str = None) -> str:
        """Upload file to storage and return presigned download URL"""
        
        if bucket is None:
            bucket = self.config.out_bucket
            
        try:
            self.s3_client.upload_file(local_path, bucket, key)
            logger.info(f"Uploaded file {local_path} to {bucket}/{key}")
            
            # Generate presigned URL for download
            download_url = self.generate_presigned_download_url(key, bucket)
            return download_url
            
        except ClientError as e:
            logger.error(f"Failed to upload file {local_path}: {e}")
            raise
    
    def generate_presigned_download_url(self, key: str, bucket: str = None, expires_in: int = 604800) -> str:
        """Generate presigned URL for downloading files (default 7 days)"""
        
        if bucket is None:
            bucket = self.config.out_bucket
            
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': key},
                ExpiresIn=expires_in
            )
            return url
            
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL for {bucket}/{key}: {e}")
            raise
    
    def download_file(self, key: str, local_path: str, bucket: str = None):
        """Download file from storage"""
        
        if bucket is None:
            bucket = self.config.raw_bucket
            
        try:
            self.s3_client.download_file(bucket, key, local_path)
            logger.info(f"Downloaded {bucket}/{key} to {local_path}")
            
        except ClientError as e:
            logger.error(f"Failed to download {bucket}/{key}: {e}")
            raise
    
    def get_object_info(self, key: str, bucket: str = None) -> Dict:
        """Get object metadata"""
        
        if bucket is None:
            bucket = self.config.raw_bucket
            
        try:
            response = self.s3_client.head_object(Bucket=bucket, Key=key)
            return {
                'size': response.get('ContentLength'),
                'etag': response.get('ETag'),
                'last_modified': response.get('LastModified'),
                'content_type': response.get('ContentType')
            }
            
        except ClientError as e:
            logger.error(f"Failed to get object info for {bucket}/{key}: {e}")
            raise
    
    def calculate_file_hash(self, local_path: str) -> str:
        """Calculate SHA256 hash of local file"""
        
        sha256_hash = hashlib.sha256()
        with open(local_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()


# Global storage manager instance
storage_manager = StorageManager()