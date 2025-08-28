"""
Configuration management for dual-mode operation (LOCAL vs PRODUCTION)
"""
import os
from enum import Enum
from typing import Optional
from dataclasses import dataclass


class Environment(Enum):
    LOCAL = "local"
    PRODUCTION = "production"


@dataclass
class StorageConfig:
    """Storage configuration for different environments"""
    # S3/MinIO configuration
    endpoint_url: Optional[str]
    access_key: str
    secret_key: str
    region: str
    raw_bucket: str
    out_bucket: str
    use_ssl: bool = True
    
    # Upload configuration
    multipart_threshold: int = 64 * 1024 * 1024  # 64MB
    multipart_chunksize: int = 64 * 1024 * 1024  # 64MB
    max_concurrency: int = 10
    use_transfer_acceleration: bool = False


@dataclass
class DatabaseConfig:
    """Database configuration"""
    url: str
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30


@dataclass
class QueueConfig:
    """Queue configuration for job processing"""
    type: str  # 'redis' for local, 'sqs' for production
    url: str
    visibility_timeout: int = 900
    max_retries: int = 3


@dataclass
class BatchConfig:
    """Batch job configuration"""
    cpu_queue: str
    gpu_queue: str
    cpu_job_definition: str
    gpu_job_definition: str


@dataclass
class AppConfig:
    """Main application configuration"""
    environment: Environment
    storage: StorageConfig
    database: DatabaseConfig
    queue: QueueConfig
    batch: Optional[BatchConfig] = None
    
    # Upload server configuration
    tusd_url: Optional[str] = None
    tusd_internal_url: Optional[str] = None


def get_config() -> AppConfig:
    """Get configuration based on environment variables"""
    
    # Determine environment
    env_name = os.getenv("ENVIRONMENT", "local").lower()
    environment = Environment.LOCAL if env_name == "local" else Environment.PRODUCTION
    
    if environment == Environment.LOCAL:
        return _get_local_config()
    else:
        return _get_production_config()


def _get_local_config() -> AppConfig:
    """Configuration for local development with MinIO + Redis + tusd"""
    
    storage = StorageConfig(
        endpoint_url=os.getenv("MINIO_ENDPOINT", "http://minio:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        region=os.getenv("MINIO_REGION", "us-east-1"),
        raw_bucket=os.getenv("MINIO_UPLOADS_BUCKET", "uploads"),
        out_bucket=os.getenv("MINIO_RESULTS_BUCKET", "results"),
        use_ssl=False,
        multipart_threshold=10 * 1024 * 1024,  # 10MB for local testing
        multipart_chunksize=10 * 1024 * 1024,  # 10MB
        max_concurrency=3,
        use_transfer_acceleration=False
    )
    
    database = DatabaseConfig(
        url=os.getenv("DATABASE_URL", "sqlite:///./sudoai_local.db"),
        pool_size=5,
        max_overflow=10
    )
    
    queue = QueueConfig(
        type="redis",
        url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        visibility_timeout=600,  # 10 minutes for local
        max_retries=2
    )
    
    return AppConfig(
        environment=Environment.LOCAL,
        storage=storage,
        database=database,
        queue=queue,
        tusd_url=os.getenv("TUSD_PUBLIC_URL", "http://localhost:8080"),
        tusd_internal_url=os.getenv("TUSD_INTERNAL_URL", "http://tusd:1080")
    )


def _get_production_config() -> AppConfig:
    """Configuration for production with AWS services"""
    
    aws_region = os.getenv("AWS_REGION", "ap-south-1")
    
    storage = StorageConfig(
        endpoint_url=None,  # Use default AWS S3 endpoints
        access_key=os.getenv("AWS_ACCESS_KEY_ID", ""),
        secret_key=os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        region=aws_region,
        raw_bucket=os.getenv("AWS_S3_BUCKET_RAW", ""),
        out_bucket=os.getenv("AWS_S3_BUCKET_OUT", ""),
        use_ssl=True,
        multipart_threshold=64 * 1024 * 1024,  # 64MB
        multipart_chunksize=128 * 1024 * 1024,  # 128MB for production
        max_concurrency=10,
        use_transfer_acceleration=True
    )
    
    database = DatabaseConfig(
        url=os.getenv("DATABASE_URL", ""),
        pool_size=20,
        max_overflow=40,
        pool_timeout=60
    )
    
    queue = QueueConfig(
        type="sqs",
        url=os.getenv("AWS_SQS_QUEUE_URL", ""),
        visibility_timeout=900,  # 15 minutes
        max_retries=3
    )
    
    batch = BatchConfig(
        cpu_queue=os.getenv("AWS_BATCH_CPU_QUEUE", ""),
        gpu_queue=os.getenv("AWS_BATCH_GPU_QUEUE", ""),
        cpu_job_definition=os.getenv("AWS_BATCH_CPU_JOB_DEFINITION", ""),
        gpu_job_definition=os.getenv("AWS_BATCH_GPU_JOB_DEFINITION", "")
    )
    
    return AppConfig(
        environment=Environment.PRODUCTION,
        storage=storage,
        database=database,
        queue=queue,
        batch=batch
    )


# Global config instance
config = get_config()