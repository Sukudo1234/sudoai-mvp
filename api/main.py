"""
Enhanced sudo.ai MVP API with dual-mode support (LOCAL: tusd+MinIO, PRODUCTION: S3+SQS+Batch)
Maintains exact API contract while supporting both environments
"""
import os
import sys
import uuid
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from loguru import logger
from contextlib import asynccontextmanager

# Add the parent directory to Python path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config import config, Environment
from shared.upload_service import upload_service
from shared.queue_manager import queue_manager
from shared.database import JobType, db_manager
from shared.storage_manager import storage_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    logger.info(f"Starting sudo.ai API in {config.environment.value} mode")
    logger.info(f"Database: {config.database.url}")
    logger.info(f"Storage: {config.storage.raw_bucket} / {config.storage.out_bucket}")
    logger.info(f"Queue: {config.queue.type} - {config.queue.url}")
    
    yield
    
    logger.info("Shutting down sudo.ai API")


app = FastAPI(
    title="sudo.ai MVP API", 
    version="0.2.0",
    description="Production-ready media processing API with dual-mode infrastructure",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to actual frontend domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===== REQUEST/RESPONSE MODELS =====

class SplitReq(BaseModel):
    """Request model for audio splitting"""
    tus_url: str = Field(..., description="Full upload URL (tusd Location or S3 URL)")
    
    @validator('tus_url')
    def validate_url(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("tus_url must be a valid string")
        return v


class MergeReq(BaseModel):
    """Request model for video/audio merging"""
    video_tus_url: str = Field(..., description="Video file upload URL")
    audio_tus_url: str = Field(..., description="Audio file upload URL")
    offset_sec: float = Field(default=0.0, description="Audio offset in seconds")


class TranscribeReq(BaseModel):
    """Request model for transcription"""
    tus_url: str = Field(..., description="Audio/video file upload URL")
    target_languages: List[str] = Field(default_factory=lambda: ["original"], description="Target languages")


class RenameReq(BaseModel):
    """Request model for batch file renaming"""
    keys: List[str] = Field(..., description="List of S3 keys to rename")
    pattern: str = Field(..., description="Rename pattern with {index}, {basename}, {ext} placeholders")
    start_index: int = Field(default=1, description="Starting index for numbering")
    pad: int = Field(default=2, description="Zero padding for numbers")
    dryRun: bool = Field(default=False, description="Preview changes without applying")


class MultipartUploadInitRequest(BaseModel):
    """Request model for initiating multipart upload"""
    filename: str = Field(..., description="Original filename")
    file_size: int = Field(..., gt=0, description="File size in bytes")
    content_type: Optional[str] = Field(None, description="MIME type")


class MultipartUploadCompleteRequest(BaseModel):
    """Request model for completing multipart upload"""
    key: str = Field(..., description="S3 object key")
    upload_id: str = Field(..., description="Upload ID from initiation")
    parts: List[Dict[str, Any]] = Field(..., description="List of completed parts with part_number and etag")


class JobResponse(BaseModel):
    """Standard job response model"""
    task_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


# ===== HEALTH & INFO ENDPOINTS =====

@app.get("/health")
def health():
    """Health check endpoint"""
    try:
        # Test database connection
        stats = db_manager.get_job_stats()
        
        return {
            "ok": True,
            "environment": config.environment.value,
            "version": "0.2.0",
            "storage": {
                "type": "s3" if config.environment == Environment.PRODUCTION else "minio",
                "raw_bucket": config.storage.raw_bucket,
                "out_bucket": config.storage.out_bucket
            },
            "queue": {
                "type": config.queue.type,
                "url": config.queue.url if config.environment == Environment.LOCAL else "sqs"
            },
            "job_stats": stats
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")


# ===== UPLOAD ENDPOINTS =====

@app.get("/uploads/tus")
def get_tus():
    """Get TUS upload configuration (maintains compatibility)"""
    upload_info = upload_service.get_upload_info()
    
    if upload_info.method == 'tus':
        return {"tus_endpoint": upload_info.endpoint}
    else:
        # For S3 mode, still return compatible response but indicate multipart support
        return {
            "tus_endpoint": upload_info.endpoint,
            "multipart_supported": True,
            "method": upload_info.method,
            "metadata": upload_info.metadata
        }


@app.post("/uploads/s3/initiate")
def initiate_multipart_upload(req: MultipartUploadInitRequest):
    """Initiate S3 multipart upload (production mode only)"""
    if config.environment == Environment.LOCAL:
        raise HTTPException(
            status_code=400, 
            detail="S3 multipart uploads not supported in local mode. Use /uploads/tus endpoint."
        )
    
    try:
        result = upload_service.initiate_multipart_upload(
            req.filename, req.file_size, req.content_type
        )
        
        return {
            "upload_id": result.upload_id,
            "key": result.key,
            "presigned_urls": result.presigned_urls,
            "complete_url": result.complete_url,
            "abort_url": result.abort_url,
            "metadata": {
                "chunk_size": config.storage.multipart_chunksize,
                "max_concurrent": config.storage.max_concurrency
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to initiate multipart upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/uploads/s3/complete")
def complete_multipart_upload(req: MultipartUploadCompleteRequest):
    """Complete S3 multipart upload (production mode only)"""
    if config.environment == Environment.LOCAL:
        raise HTTPException(
            status_code=400, 
            detail="S3 multipart uploads not supported in local mode."
        )
    
    try:
        result = upload_service.complete_multipart_upload(
            req.key, req.upload_id, req.parts
        )
        return result
        
    except Exception as e:
        logger.error(f"Failed to complete multipart upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/uploads/s3/abort")
def abort_multipart_upload(key: str, upload_id: str):
    """Abort S3 multipart upload (production mode only)"""
    if config.environment == Environment.LOCAL:
        raise HTTPException(
            status_code=400, 
            detail="S3 multipart uploads not supported in local mode."
        )
    
    try:
        upload_service.abort_multipart_upload(key, upload_id)
        return {"success": True, "message": "Upload aborted"}
        
    except Exception as e:
        logger.error(f"Failed to abort multipart upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== JOB PROCESSING ENDPOINTS (EXACT API CONTRACT MAINTAINED) =====

@app.post("/split", response_model=Dict[str, str])
def split(req: SplitReq):
    """Split audio tracks using Demucs (GPU job)"""
    try:
        input_params = {"tus_url": req.tus_url}
        
        # Generate idempotency key based on input
        idempotency_key = f"split-{hash(req.tus_url)}"
        
        task_id = queue_manager.send_job(
            JobType.SPLIT, 
            input_params, 
            idempotency_key=idempotency_key
        )
        
        logger.info(f"Submitted split job {task_id} for URL {req.tus_url}")
        return {"task_id": task_id}
        
    except Exception as e:
        logger.error(f"Failed to submit split job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/merge", response_model=Dict[str, str])
def merge(req: MergeReq):
    """Merge video and audio tracks (CPU job)"""
    try:
        input_params = {
            "video_tus_url": req.video_tus_url,
            "audio_tus_url": req.audio_tus_url,
            "offset_sec": req.offset_sec
        }
        
        # Generate idempotency key based on input
        idempotency_key = f"merge-{hash((req.video_tus_url, req.audio_tus_url, req.offset_sec))}"
        
        task_id = queue_manager.send_job(
            JobType.MERGE, 
            input_params, 
            idempotency_key=idempotency_key
        )
        
        logger.info(f"Submitted merge job {task_id}")
        return {"task_id": task_id}
        
    except Exception as e:
        logger.error(f"Failed to submit merge job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transcribe", response_model=Dict[str, str])
def transcribe(req: TranscribeReq):
    """Transcribe audio/video using ElevenLabs (CPU job)"""
    try:
        input_params = {
            "tus_url": req.tus_url,
            "target_languages": req.target_languages
        }
        
        # Generate idempotency key based on input
        idempotency_key = f"transcribe-{hash((req.tus_url, tuple(req.target_languages)))}"
        
        task_id = queue_manager.send_job(
            JobType.TRANSCRIBE, 
            input_params, 
            idempotency_key=idempotency_key
        )
        
        logger.info(f"Submitted transcribe job {task_id}")
        return {"task_id": task_id}
        
    except Exception as e:
        logger.error(f"Failed to submit transcribe job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rename", response_model=Dict[str, str])
def rename(req: RenameReq):
    """Batch rename files in storage (CPU job)"""
    try:
        input_params = {
            "keys": req.keys,
            "pattern": req.pattern,
            "start_index": req.start_index,
            "pad": req.pad,
            "dryRun": req.dryRun
        }
        
        # Generate idempotency key based on input
        idempotency_key = f"rename-{hash((tuple(req.keys), req.pattern, req.start_index, req.pad))}"
        
        task_id = queue_manager.send_job(
            JobType.RENAME, 
            input_params, 
            idempotency_key=idempotency_key
        )
        
        logger.info(f"Submitted rename job {task_id}")
        return {"task_id": task_id}
        
    except Exception as e:
        logger.error(f"Failed to submit rename job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{task_id}")
def get_job(task_id: str):
    """Get job status and results (maintains exact API contract)"""
    try:
        job_info = queue_manager.get_job_status(task_id)
        
        if not job_info or job_info.get('status') in ['not_found', 'unknown']:
            raise HTTPException(status_code=404, detail=f"Job {task_id} not found")
        
        # Transform response to match original API contract
        response = {
            "task_id": task_id,
            "state": job_info.get('status', 'UNKNOWN').upper()
        }
        
        # Map status values to match original Celery format
        status_mapping = {
            'pending': 'PENDING',
            'queued': 'PENDING', 
            'running': 'STARTED',
            'completed': 'SUCCESS',
            'failed': 'FAILURE',
            'cancelled': 'REVOKED'
        }
        
        response["state"] = status_mapping.get(job_info.get('status'), 'UNKNOWN')
        
        if response["state"] == "SUCCESS":
            response["result"] = job_info.get('result')
        elif response["state"] == "FAILURE":
            response["error"] = job_info.get('error_message', 'Unknown error')
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job status for {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== ADDITIONAL PRODUCTION ENDPOINTS =====

@app.get("/jobs", response_model=Dict[str, Any])
def list_jobs(
    status: Optional[str] = None,
    job_type: Optional[str] = None, 
    limit: int = 50,
    offset: int = 0
):
    """List jobs with filtering (new endpoint for production UI)"""
    try:
        # Convert string parameters to enums if provided
        status_filter = None
        type_filter = None
        
        if status:
            try:
                from shared.database import JobStatus
                status_filter = JobStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        if job_type:
            try:
                type_filter = JobType(job_type)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid job_type: {job_type}")
        
        jobs = db_manager.get_jobs(status_filter, type_filter, limit, offset)
        job_list = [job.to_dict() for job in jobs]
        
        stats = db_manager.get_job_stats()
        
        return {
            "jobs": job_list,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total": sum(stats.values())
            },
            "stats": stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/requeue/{task_id}")
def requeue_job(task_id: str, background_tasks: BackgroundTasks):
    """Requeue a failed job (admin endpoint)"""
    try:
        job = db_manager.get_job_by_task_id(task_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job.status not in ['failed', 'cancelled']:
            raise HTTPException(status_code=400, detail="Only failed or cancelled jobs can be requeued")
        
        # Create new job with same parameters
        new_task_id = queue_manager.send_job(
            JobType(job.job_type),
            job.input_params
        )
        
        logger.info(f"Requeued job {task_id} as {new_task_id}")
        return {"original_task_id": task_id, "new_task_id": new_task_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to requeue job {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/stats")
def get_system_stats():
    """Get system statistics (admin endpoint)"""
    try:
        job_stats = db_manager.get_job_stats()
        
        # Get storage stats if available
        storage_info = {
            "environment": config.environment.value,
            "raw_bucket": config.storage.raw_bucket,
            "out_bucket": config.storage.out_bucket,
            "multipart_threshold": config.storage.multipart_threshold,
            "transfer_acceleration": config.storage.use_transfer_acceleration
        }
        
        queue_info = {
            "type": config.queue.type,
            "visibility_timeout": config.queue.visibility_timeout,
            "max_retries": config.queue.max_retries
        }
        
        return {
            "jobs": job_stats,
            "storage": storage_info,
            "queue": queue_info,
            "batch": {
                "cpu_queue": getattr(config.batch, 'cpu_queue', None),
                "gpu_queue": getattr(config.batch, 'gpu_queue', None)
            } if config.batch else None
        }
        
    except Exception as e:
        logger.error(f"Failed to get system stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_level="info",
        access_log=True
    )