"""
Database management with job persistence for production environment
"""
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from sqlalchemy import create_engine, Column, String, DateTime, Text, Integer, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import UUID
from loguru import logger

from .config import config


Base = declarative_base()


class JobStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(Enum):
    SPLIT = "split"
    MERGE = "merge"
    TRANSCRIBE = "transcribe"
    RENAME = "rename"


class Job(Base):
    """Job model for tracking processing tasks"""
    __tablename__ = "jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(String(255), unique=True, nullable=False, index=True)  # Celery/SQS task ID
    job_type = Column(String(50), nullable=False)  # split, merge, transcribe, rename
    status = Column(String(50), nullable=False, default=JobStatus.PENDING.value)
    
    # Input parameters (stored as JSON)
    input_params = Column(JSON, nullable=False)
    
    # Results (stored as JSON when completed)
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Idempotency and deduplication
    input_hash = Column(String(64), nullable=False, index=True)  # SHA256 of input params
    
    # Timing information
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # AWS Batch information (production only)
    batch_job_id = Column(String(255), nullable=True)
    batch_job_queue = Column(String(255), nullable=True)
    
    # Retry information
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    
    # Add composite indexes for common queries
    __table_args__ = (
        Index('ix_job_status_created', 'status', 'created_at'),
        Index('ix_job_type_status', 'job_type', 'status'),
        Index('ix_input_hash_status', 'input_hash', 'status'),
    )
    
    def to_dict(self) -> Dict:
        """Convert job to dictionary for API responses"""
        return {
            'id': str(self.id),
            'task_id': self.task_id,
            'job_type': self.job_type,
            'status': self.status,
            'input_params': self.input_params,
            'result': self.result,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries
        }


class DatabaseManager:
    """Database manager for job persistence and queries"""
    
    def __init__(self):
        self.config = config.database
        self.engine = create_engine(
            self.config.url,
            pool_size=self.config.pool_size,
            max_overflow=self.config.max_overflow,
            pool_timeout=self.config.pool_timeout,
            echo=False  # Set to True for SQL debugging
        )
        
        # Create session factory
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        # Create tables
        self._create_tables()
        
        logger.info("Database manager initialized")
    
    def _create_tables(self):
        """Create database tables"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created/verified")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
    
    def get_session(self) -> Session:
        """Get database session"""
        return self.SessionLocal()
    
    def create_job(
        self, 
        task_id: str,
        job_type: JobType,
        input_params: Dict[str, Any],
        input_hash: str
    ) -> Job:
        """Create a new job record"""
        
        with self.get_session() as session:
            try:
                job = Job(
                    task_id=task_id,
                    job_type=job_type.value,
                    status=JobStatus.PENDING.value,
                    input_params=input_params,
                    input_hash=input_hash
                )
                
                session.add(job)
                session.commit()
                session.refresh(job)
                
                logger.info(f"Created job {job.id} with task_id {task_id}")
                return job
                
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to create job: {e}")
                raise
    
    def get_job_by_task_id(self, task_id: str) -> Optional[Job]:
        """Get job by task ID"""
        
        with self.get_session() as session:
            return session.query(Job).filter(Job.task_id == task_id).first()
    
    def get_job_by_id(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        
        with self.get_session() as session:
            return session.query(Job).filter(Job.id == job_id).first()
    
    def find_duplicate_job(self, input_hash: str, job_type: JobType) -> Optional[Job]:
        """Find existing job with same input hash and type"""
        
        with self.get_session() as session:
            return session.query(Job).filter(
                Job.input_hash == input_hash,
                Job.job_type == job_type.value,
                Job.status.in_([JobStatus.COMPLETED.value, JobStatus.RUNNING.value, JobStatus.QUEUED.value])
            ).first()
    
    def update_job_status(
        self, 
        task_id: str, 
        status: JobStatus, 
        result: Optional[Dict] = None,
        error_message: Optional[str] = None,
        batch_job_id: Optional[str] = None
    ) -> bool:
        """Update job status and related fields"""
        
        with self.get_session() as session:
            try:
                job = session.query(Job).filter(Job.task_id == task_id).first()
                if not job:
                    logger.warning(f"Job with task_id {task_id} not found")
                    return False
                
                job.status = status.value
                
                if status == JobStatus.RUNNING and not job.started_at:
                    job.started_at = datetime.utcnow()
                
                if status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    job.completed_at = datetime.utcnow()
                
                if result is not None:
                    job.result = result
                
                if error_message is not None:
                    job.error_message = error_message
                
                if batch_job_id is not None:
                    job.batch_job_id = batch_job_id
                
                session.commit()
                logger.info(f"Updated job {job.id} status to {status.value}")
                return True
                
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to update job status: {e}")
                raise
    
    def increment_retry_count(self, task_id: str) -> bool:
        """Increment retry count for a job"""
        
        with self.get_session() as session:
            try:
                job = session.query(Job).filter(Job.task_id == task_id).first()
                if not job:
                    return False
                
                job.retry_count += 1
                session.commit()
                
                logger.info(f"Incremented retry count for job {job.id} to {job.retry_count}")
                return True
                
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to increment retry count: {e}")
                raise
    
    def get_jobs(
        self, 
        status: Optional[JobStatus] = None,
        job_type: Optional[JobType] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Job]:
        """Get jobs with optional filtering"""
        
        with self.get_session() as session:
            query = session.query(Job)
            
            if status:
                query = query.filter(Job.status == status.value)
            
            if job_type:
                query = query.filter(Job.job_type == job_type.value)
            
            query = query.order_by(Job.created_at.desc())
            query = query.offset(offset).limit(limit)
            
            return query.all()
    
    def get_job_stats(self) -> Dict[str, int]:
        """Get job statistics by status"""
        
        with self.get_session() as session:
            stats = {}
            
            for status in JobStatus:
                count = session.query(Job).filter(Job.status == status.value).count()
                stats[status.value] = count
            
            return stats
    
    def cleanup_old_jobs(self, days_old: int = 30) -> int:
        """Clean up old completed/failed jobs"""
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        with self.get_session() as session:
            try:
                deleted = session.query(Job).filter(
                    Job.status.in_([JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value]),
                    Job.completed_at < cutoff_date
                ).delete()
                
                session.commit()
                logger.info(f"Cleaned up {deleted} old jobs")
                return deleted
                
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to cleanup old jobs: {e}")
                raise


# Global database manager instance
db_manager = DatabaseManager()