"""
Queue management supporting both Redis (local) and SQS (production)
with unified interface for job processing
"""
import json
import uuid
import hashlib
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
from loguru import logger

# Local imports
try:
    import redis
    import celery
    from celery import Celery
except ImportError:
    redis = None
    celery = None
    Celery = None

# AWS imports
try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = None

from .config import config, Environment
from .database import db_manager, JobType, JobStatus


@dataclass
class QueueMessage:
    """Unified queue message format"""
    job_id: str
    task_id: str
    job_type: JobType
    input_params: Dict[str, Any]
    retry_count: int = 0
    created_at: Optional[datetime] = None


class BaseQueueManager(ABC):
    """Abstract base class for queue managers"""
    
    @abstractmethod
    def send_job(self, job_type: JobType, input_params: Dict[str, Any], idempotency_key: str = None) -> str:
        """Send job to queue and return task_id"""
        pass
    
    @abstractmethod
    def get_job_status(self, task_id: str) -> Dict[str, Any]:
        """Get job status from queue/database"""
        pass


class RedisQueueManager(BaseQueueManager):
    """Redis-based queue manager using Celery (for local development)"""
    
    def __init__(self):
        if not celery:
            raise ImportError("celery package required for Redis queue manager")
        
        self.queue_config = config.queue
        self.celery_app = Celery(
            'sudoai_worker',
            broker=self.queue_config.url,
            backend=self.queue_config.url
        )
        
        # Configure Celery
        self.celery_app.conf.update(
            task_serializer='json',
            result_serializer='json',
            accept_content=['json'],
            result_expires=3600,
            task_track_started=True,
            worker_prefetch_multiplier=1
        )
        
        logger.info("Redis queue manager initialized")
    
    def send_job(self, job_type: JobType, input_params: Dict[str, Any], idempotency_key: str = None) -> str:
        """Send job to Celery queue"""
        
        # Calculate input hash for idempotency
        input_hash = self._calculate_input_hash(input_params, job_type)
        
        # Check for existing job if idempotency key provided
        if idempotency_key:
            existing_job = db_manager.find_duplicate_job(input_hash, job_type)
            if existing_job:
                logger.info(f"Found existing job {existing_job.task_id} for idempotency key {idempotency_key}")
                return existing_job.task_id
        
        # Map job types to Celery tasks
        task_mapping = {
            JobType.SPLIT: 'tasks.split_task',
            JobType.MERGE: 'tasks.merge_task',
            JobType.TRANSCRIBE: 'tasks.transcribe_task',
            JobType.RENAME: 'tasks.rename_task'
        }
        
        task_name = task_mapping.get(job_type)
        if not task_name:
            raise ValueError(f"Unsupported job type: {job_type}")
        
        # Send task to Celery
        try:
            # Prepare task arguments based on job type
            args = self._prepare_task_args(job_type, input_params)
            
            result = self.celery_app.send_task(task_name, args=args)
            task_id = result.id
            
            # Create job record in database
            db_manager.create_job(task_id, job_type, input_params, input_hash)
            
            logger.info(f"Sent {job_type.value} job to Celery with task_id {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to send job to Celery: {e}")
            raise
    
    def get_job_status(self, task_id: str) -> Dict[str, Any]:
        """Get job status from Celery result backend"""
        
        try:
            # Get job from database first
            job = db_manager.get_job_by_task_id(task_id)
            if job:
                return job.to_dict()
            
            # Fall back to Celery result backend
            result = self.celery_app.AsyncResult(task_id)
            
            status_mapping = {
                'PENDING': JobStatus.PENDING.value,
                'STARTED': JobStatus.RUNNING.value,
                'SUCCESS': JobStatus.COMPLETED.value,
                'FAILURE': JobStatus.FAILED.value,
                'RETRY': JobStatus.QUEUED.value,
                'REVOKED': JobStatus.CANCELLED.value
            }
            
            response = {
                'task_id': task_id,
                'status': status_mapping.get(result.state, result.state),
            }
            
            if result.state == 'SUCCESS':
                response['result'] = result.result
            elif result.state == 'FAILURE':
                response['error'] = str(result.info)
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to get job status for {task_id}: {e}")
            return {'task_id': task_id, 'status': 'unknown', 'error': str(e)}
    
    def _prepare_task_args(self, job_type: JobType, input_params: Dict[str, Any]) -> List[Any]:
        """Prepare task arguments based on job type"""
        
        if job_type == JobType.SPLIT:
            return [input_params['tus_url']]
        elif job_type == JobType.MERGE:
            return [
                input_params['video_tus_url'],
                input_params['audio_tus_url'],
                input_params.get('offset_sec', 0.0)
            ]
        elif job_type == JobType.TRANSCRIBE:
            return [
                input_params['tus_url'],
                input_params.get('target_languages', ['original'])
            ]
        elif job_type == JobType.RENAME:
            return [
                input_params['keys'],
                input_params['pattern'],
                input_params.get('start_index', 1),
                input_params.get('pad', 2),
                input_params.get('dryRun', False)
            ]
        else:
            raise ValueError(f"Unsupported job type: {job_type}")
    
    def _calculate_input_hash(self, input_params: Dict[str, Any], job_type: JobType) -> str:
        """Calculate SHA256 hash of input parameters for idempotency"""
        
        # Create a stable representation of input params
        stable_params = {
            'job_type': job_type.value,
            'params': input_params
        }
        
        content = json.dumps(stable_params, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()


class SQSQueueManager(BaseQueueManager):
    """SQS-based queue manager for production AWS environment"""
    
    def __init__(self):
        if not boto3:
            raise ImportError("boto3 package required for SQS queue manager")
        
        self.queue_config = config.queue
        self.batch_config = config.batch
        
        # Initialize AWS clients
        self.sqs = boto3.client('sqs', region_name=config.storage.region)
        self.batch = boto3.client('batch', region_name=config.storage.region)
        
        logger.info("SQS queue manager initialized")
    
    def send_job(self, job_type: JobType, input_params: Dict[str, Any], idempotency_key: str = None) -> str:
        """Send job to SQS queue and submit to AWS Batch"""
        
        # Calculate input hash for idempotency
        input_hash = self._calculate_input_hash(input_params, job_type)
        
        # Check for existing job if idempotency key provided
        if idempotency_key:
            existing_job = db_manager.find_duplicate_job(input_hash, job_type)
            if existing_job:
                logger.info(f"Found existing job {existing_job.task_id} for idempotency key {idempotency_key}")
                return existing_job.task_id
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        try:
            # Create job record in database first
            job = db_manager.create_job(task_id, job_type, input_params, input_hash)
            
            # Send message to SQS queue
            message = QueueMessage(
                job_id=str(job.id),
                task_id=task_id,
                job_type=job_type,
                input_params=input_params,
                created_at=datetime.utcnow()
            )
            
            self._send_sqs_message(message, idempotency_key)
            
            # Submit to AWS Batch
            batch_job_id = self._submit_batch_job(task_id, job_type, input_params)
            
            # Update job with batch job ID
            db_manager.update_job_status(
                task_id, 
                JobStatus.QUEUED, 
                batch_job_id=batch_job_id
            )
            
            logger.info(f"Sent {job_type.value} job to SQS/Batch with task_id {task_id}, batch_job_id {batch_job_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to send job to SQS/Batch: {e}")
            # Mark job as failed if it was created
            try:
                db_manager.update_job_status(task_id, JobStatus.FAILED, error_message=str(e))
            except:
                pass
            raise
    
    def get_job_status(self, task_id: str) -> Dict[str, Any]:
        """Get job status from database and AWS Batch"""
        
        try:
            # Get job from database
            job = db_manager.get_job_by_task_id(task_id)
            if not job:
                return {'task_id': task_id, 'status': 'not_found'}
            
            job_dict = job.to_dict()
            
            # If job is running, get additional info from Batch
            if job.status == JobStatus.RUNNING.value and job.batch_job_id:
                try:
                    batch_response = self.batch.describe_jobs(jobs=[job.batch_job_id])
                    if batch_response['jobs']:
                        batch_job = batch_response['jobs'][0]
                        job_dict['batch_status'] = batch_job['status']
                        job_dict['batch_created_at'] = batch_job.get('createdAt')
                        job_dict['batch_started_at'] = batch_job.get('startedAt')
                        
                        # Update job status based on Batch status
                        batch_status = batch_job['status']
                        if batch_status == 'SUCCEEDED':
                            # Job completed - this should be handled by worker callback
                            pass
                        elif batch_status == 'FAILED':
                            db_manager.update_job_status(
                                task_id, 
                                JobStatus.FAILED,
                                error_message=batch_job.get('statusReason', 'Batch job failed')
                            )
                            job_dict['status'] = JobStatus.FAILED.value
                            
                except Exception as e:
                    logger.warning(f"Failed to get Batch status for job {batch_job_id}: {e}")
            
            return job_dict
            
        except Exception as e:
            logger.error(f"Failed to get job status for {task_id}: {e}")
            return {'task_id': task_id, 'status': 'error', 'error': str(e)}
    
    def _send_sqs_message(self, message: QueueMessage, idempotency_key: str = None):
        """Send message to SQS queue"""
        
        message_body = {
            'job_id': message.job_id,
            'task_id': message.task_id,
            'job_type': message.job_type.value,
            'input_params': message.input_params,
            'retry_count': message.retry_count,
            'created_at': message.created_at.isoformat() if message.created_at else None
        }
        
        sqs_params = {
            'QueueUrl': self.queue_config.url,
            'MessageBody': json.dumps(message_body)
        }
        
        # Add deduplication for FIFO queues
        if idempotency_key:
            sqs_params['MessageDeduplicationId'] = idempotency_key
            sqs_params['MessageGroupId'] = message.job_type.value
        
        try:
            response = self.sqs.send_message(**sqs_params)
            logger.debug(f"Sent SQS message {response['MessageId']} for task {message.task_id}")
            
        except ClientError as e:
            logger.error(f"Failed to send SQS message: {e}")
            raise
    
    def _submit_batch_job(self, task_id: str, job_type: JobType, input_params: Dict[str, Any]) -> str:
        """Submit job to AWS Batch"""
        
        # Determine if this is a GPU or CPU job
        job_queue = self.batch_config.gpu_queue if job_type == JobType.SPLIT else self.batch_config.cpu_queue
        job_definition = self.batch_config.gpu_job_definition if job_type == JobType.SPLIT else self.batch_config.cpu_job_definition
        
        job_name = f"{job_type.value}-{task_id[:8]}"
        
        # Prepare job parameters
        parameters = {
            'task_id': task_id,
            'job_type': job_type.value,
            'input_params': json.dumps(input_params)
        }
        
        try:
            response = self.batch.submit_job(
                jobName=job_name,
                jobQueue=job_queue,
                jobDefinition=job_definition,
                parameters=parameters,
                tags={
                    'TaskId': task_id,
                    'JobType': job_type.value,
                    'Environment': 'production'
                }
            )
            
            batch_job_id = response['jobId']
            logger.info(f"Submitted Batch job {batch_job_id} for task {task_id}")
            return batch_job_id
            
        except ClientError as e:
            logger.error(f"Failed to submit Batch job: {e}")
            raise
    
    def _calculate_input_hash(self, input_params: Dict[str, Any], job_type: JobType) -> str:
        """Calculate SHA256 hash of input parameters for idempotency"""
        
        # Create a stable representation of input params
        stable_params = {
            'job_type': job_type.value,
            'params': input_params
        }
        
        content = json.dumps(stable_params, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()


def create_queue_manager() -> BaseQueueManager:
    """Factory function to create appropriate queue manager"""
    
    if config.environment == Environment.LOCAL:
        return RedisQueueManager()
    else:
        return SQSQueueManager()


# Global queue manager instance
queue_manager = create_queue_manager()