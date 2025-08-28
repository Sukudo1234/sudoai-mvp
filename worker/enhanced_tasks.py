"""
Enhanced worker tasks supporting both local (Celery) and production (AWS Batch) environments
with unified task processing and status reporting
"""
import os
import sys
import json
import tempfile
import subprocess
import shutil
import pathlib
import time
from typing import Dict, Any, Tuple, Optional
from loguru import logger
from datetime import datetime

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config import config, Environment
from shared.storage_manager import storage_manager
from shared.database import db_manager, JobStatus, JobType
from shared.tusd import fetch_tus_file


class TaskProcessor:
    """Unified task processor for both local and production environments"""
    
    def __init__(self):
        self.config = config
        self.storage = storage_manager
        self.db = db_manager
        
        # Setup logging
        logger.add(
            "/tmp/worker.log", 
            rotation="10 MB", 
            retention="7 days",
            format="{time} | {level} | {message}"
        )
        
        logger.info(f"Worker initialized in {self.config.environment.value} mode")
    
    def run_command(self, cmd: list, timeout: int = 3600) -> str:
        """Execute shell command with timeout and logging"""
        logger.info(f"RUN: {' '.join(cmd)}")
        
        try:
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=True
            )
            
            logger.info(f"Command completed successfully: {cmd[0]}")
            return process.stdout
            
        except subprocess.CalledProcessError as e:
            error_msg = f"Command failed [{e.returncode}]: {' '.join(cmd)}\n{e.stdout}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except subprocess.TimeoutExpired as e:
            error_msg = f"Command timed out after {timeout}s: {' '.join(cmd)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def download_input_file(self, url: str) -> Tuple[str, str]:
        """Download input file from tusd or S3 based on URL format"""
        
        if url.startswith('s3://'):
            return self._download_from_s3(url)
        else:
            return self._download_from_tusd(url)
    
    def _download_from_s3(self, s3_url: str) -> Tuple[str, str]:
        """Download file from S3"""
        # Parse S3 URL: s3://bucket/key
        parts = s3_url.replace('s3://', '').split('/', 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid S3 URL format: {s3_url}")
        
        bucket, key = parts
        filename = os.path.basename(key)
        
        # Create temporary file with proper extension
        suffix = os.path.splitext(filename)[1] or '.bin'
        local_path = tempfile.NamedTemporaryFile(delete=False, suffix=suffix).name
        
        try:
            self.storage.download_file(key, local_path, bucket)
            logger.info(f"Downloaded S3 file {s3_url} to {local_path}")
            return local_path, filename
            
        except Exception as e:
            if os.path.exists(local_path):
                os.remove(local_path)
            raise RuntimeError(f"Failed to download S3 file {s3_url}: {e}")
    
    def _download_from_tusd(self, tus_url: str) -> Tuple[str, str]:
        """Download file from tusd (local mode)"""
        try:
            return fetch_tus_file(tus_url)
        except Exception as e:
            raise RuntimeError(f"Failed to download tusd file {tus_url}: {e}")
    
    def upload_result_file(self, local_path: str, job_id: str, filename: str) -> str:
        """Upload result file to storage and return download URL"""
        
        # Generate output key
        timestamp = int(time.time())
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        key = f"out/{job_id}/{timestamp}_{safe_filename}"
        
        try:
            download_url = self.storage.upload_file(local_path, key)
            logger.info(f"Uploaded result file to {key}")
            return download_url
            
        except Exception as e:
            raise RuntimeError(f"Failed to upload result file: {e}")
    
    def update_job_status(self, task_id: str, status: JobStatus, **kwargs):
        """Update job status in database"""
        try:
            self.db.update_job_status(task_id, status, **kwargs)
        except Exception as e:
            logger.error(f"Failed to update job status: {e}")
    
    # ===== TASK IMPLEMENTATIONS =====
    
    def split_task(self, task_id: str, tus_url: str) -> Dict[str, Any]:
        """Audio separation using Demucs (GPU task)"""
        
        self.update_job_status(task_id, JobStatus.RUNNING)
        logger.info(f"Starting split task {task_id} for {tus_url}")
        
        local_file = None
        wav_file = None
        output_dir = None
        
        try:
            # Download input file
            local_file, filename = self.download_input_file(tus_url)
            
            # Convert to WAV format for Demucs
            wav_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
            self.run_command([
                "ffmpeg", "-y", "-i", local_file, 
                "-ac", "2", "-ar", "44100", wav_file
            ])
            
            # Run Demucs separation
            output_dir = tempfile.mkdtemp()
            self.run_command([
                "python", "-m", "demucs.separate",
                "-o", output_dir,
                "--two-stems", "vocals",
                wav_file
            ])
            
            # Collect results
            results = {}
            demucs_root = pathlib.Path(output_dir)
            output_files = list(demucs_root.rglob("*.wav"))
            
            for output_file in output_files:
                # Upload each separated track
                track_name = output_file.stem
                download_url = self.upload_result_file(
                    str(output_file), 
                    task_id, 
                    f"{track_name}.wav"
                )
                
                results[track_name] = {
                    "key": f"out/{task_id}/{track_name}.wav",
                    "url": download_url
                }
            
            result = {
                "filename": filename,
                "results": results
            }
            
            self.update_job_status(task_id, JobStatus.COMPLETED, result=result)
            logger.info(f"Completed split task {task_id}")
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Split task {task_id} failed: {error_msg}")
            self.update_job_status(task_id, JobStatus.FAILED, error_message=error_msg)
            raise
        finally:
            # Cleanup temporary files
            for temp_file in [local_file, wav_file]:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
            if output_dir and os.path.exists(output_dir):
                try:
                    shutil.rmtree(output_dir)
                except:
                    pass


# Global task processor instance
task_processor = TaskProcessor()


# ===== CELERY TASK WRAPPERS (for local development) =====

if config.environment == Environment.LOCAL:
    try:
        from celery import Celery
        
        celery_app = Celery(
            'enhanced_worker',
            broker=config.queue.url,
            backend=config.queue.url
        )
        
        celery_app.conf.update(
            task_serializer='json',
            result_serializer='json', 
            accept_content=['json'],
            result_expires=3600,
            task_track_started=True,
            worker_prefetch_multiplier=1
        )
        
        @celery_app.task(name="tasks.split_task")
        def split_task_celery(tus_url: str):
            task_id = split_task_celery.request.id
            return task_processor.split_task(task_id, tus_url)
        
        logger.info("Celery tasks registered for local development")
        
    except ImportError:
        logger.warning("Celery not available - running in production Batch mode")


# ===== AWS BATCH ENTRY POINT (for production) =====

def batch_main():
    """Entry point for AWS Batch jobs"""
    
    if len(sys.argv) < 2:
        logger.error("Usage: python enhanced_tasks.py <job_type> [task_id] [params...]")
        sys.exit(1)
    
    job_type = sys.argv[1]
    
    # Get task parameters from environment variables (set by Batch job definition)
    task_id = os.getenv('TASK_ID')
    job_params = os.getenv('INPUT_PARAMS')
    
    if not task_id or not job_params:
        logger.error("TASK_ID and INPUT_PARAMS environment variables required")
        sys.exit(1)
    
    try:
        params = json.loads(job_params)
        logger.info(f"Starting Batch job: {job_type} with task_id: {task_id}")
        
        if job_type == 'split':
            result = task_processor.split_task(task_id, params['tus_url'])
        else:
            raise ValueError(f"Unknown job type: {job_type}")
        
        logger.info(f"Batch job completed successfully: {task_id}")
        print(json.dumps(result))  # Output result for Batch job logs
        
    except Exception as e:
        logger.error(f"Batch job failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if config.environment == Environment.PRODUCTION:
        batch_main()
    else:
        logger.info("Enhanced worker loaded for local development")