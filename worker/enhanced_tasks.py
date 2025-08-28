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
    
    def merge_task(self, task_id: str, video_url: str, audio_url: str, offset_sec: float = 0.0) -> Dict[str, Any]:
        """Video/audio merging using FFmpeg (CPU task)"""
        
        self.update_job_status(task_id, JobStatus.RUNNING)
        logger.info(f"Starting merge task {task_id}")
        
        video_file = None
        audio_file = None
        output_file = None
        
        try:
            # Download input files
            video_file, video_name = self.download_input_file(video_url)
            audio_file, audio_name = self.download_input_file(audio_url)
            
            # Prepare output file
            output_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
            
            # Build FFmpeg command
            cmd = ["ffmpeg", "-y", "-i", video_file]
            
            if abs(offset_sec) > 0.0001:
                cmd.extend(["-itsoffset", str(offset_sec)])
            
            cmd.extend([
                "-i", audio_file,
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest", output_file
            ])
            
            try:
                self.run_command(cmd)
            except RuntimeError:
                # Fallback to re-encoding video if copy fails
                logger.warning("Video copy failed, trying with re-encoding")
                cmd_fallback = [
                    "ffmpeg", "-y", "-i", video_file, "-i", audio_file,
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "libx264", "-c:a", "aac",
                    "-shortest", output_file
                ]
                self.run_command(cmd_fallback)
            
            # Upload result
            merged_filename = f"{os.path.splitext(video_name)[0]}_merged.mp4"
            download_url = self.upload_result_file(output_file, task_id, merged_filename)
            
            result = {
                "video": video_name,
                "audio": audio_name,
                "result": {
                    "key": f"out/{task_id}/{merged_filename}",
                    "url": download_url
                }
            }
            
            self.update_job_status(task_id, JobStatus.COMPLETED, result=result)
            logger.info(f"Completed merge task {task_id}")
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Merge task {task_id} failed: {error_msg}")
            self.update_job_status(task_id, JobStatus.FAILED, error_message=error_msg)
            raise
        finally:
            # Cleanup temporary files
            for temp_file in [video_file, audio_file, output_file]:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
    
    def transcribe_task(self, task_id: str, tus_url: str, target_languages: list = None) -> Dict[str, Any]:
        """Audio transcription using ElevenLabs API (CPU task)"""
        
        self.update_job_status(task_id, JobStatus.RUNNING)
        logger.info(f"Starting transcribe task {task_id}")
        
        if target_languages is None:
            target_languages = ["original"]
        
        input_file = None
        wav_file = None
        
        try:
            # Download input file
            input_file, filename = self.download_input_file(tus_url)
            
            # Convert to WAV format for transcription
            wav_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
            self.run_command([
                "ffmpeg", "-y", "-i", input_file,
                "-ac", "1", "-ar", "16000", wav_file
            ])
            
            # Check if ElevenLabs is configured
            elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")
            elevenlabs_url = os.getenv("ELEVENLABS_TRANSCRIBE_URL", "")
            
            if not elevenlabs_key or not elevenlabs_url or elevenlabs_url == "REPLACE_ME":
                # Upload the processed audio file as fallback
                wav_download_url = self.upload_result_file(wav_file, task_id, f"{os.path.splitext(filename)[0]}.wav")
                
                result = {
                    "warning": "Set ELEVENLABS_API_KEY and ELEVENLABS_TRANSCRIBE_URL to enable transcription.",
                    "audio_url": wav_download_url
                }
                
                self.update_job_status(task_id, JobStatus.COMPLETED, result=result)
                return result
            
            # Call ElevenLabs transcription API
            import requests
            
            headers = {"xi-api-key": elevenlabs_key}
            files = {"file": (os.path.basename(wav_file), open(wav_file, "rb"), "audio/wav")}
            data = {
                "language": os.getenv("ELEVENLABS_LANGUAGE", "auto"),
                "output_format": os.getenv("ELEVENLABS_OUTPUT_FORMAT", "srt")
            }
            
            response = requests.post(elevenlabs_url, headers=headers, files=files, data=data)
            
            if response.status_code >= 300:
                raise RuntimeError(f"Transcription failed: {response.status_code} {response.text}")
            
            # Save transcription result
            srt_file = tempfile.NamedTemporaryFile(delete=False, suffix=".srt").name
            with open(srt_file, "wb") as f:
                f.write(response.content)
            
            # Upload transcription result
            srt_filename = f"{os.path.splitext(filename)[0]}.srt"
            srt_download_url = self.upload_result_file(srt_file, task_id, srt_filename)
            
            result = {
                "filename": filename,
                "srt": {
                    "key": f"out/{task_id}/{srt_filename}",
                    "url": srt_download_url
                }
            }
            
            self.update_job_status(task_id, JobStatus.COMPLETED, result=result)
            logger.info(f"Completed transcribe task {task_id}")
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Transcribe task {task_id} failed: {error_msg}")
            self.update_job_status(task_id, JobStatus.FAILED, error_message=error_msg)
            raise
        finally:
            # Cleanup temporary files
            for temp_file in [input_file, wav_file]:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
    
    def rename_task(self, task_id: str, keys: list, pattern: str, start_index: int = 1, pad: int = 2, dry_run: bool = False) -> Dict[str, Any]:
        """Batch file renaming in storage (CPU task)"""
        
        self.update_job_status(task_id, JobStatus.RUNNING)
        logger.info(f"Starting rename task {task_id} ({'dry run' if dry_run else 'live run'})")
        
        try:
            mapping = []
            idx = start_index
            
            for key in keys:
                base = os.path.splitext(os.path.basename(key))[0]
                ext = os.path.splitext(key)[1]
                
                newname = pattern.replace("{index}", str(idx).zfill(pad)).replace("{basename}", base).replace("{ext}", ext)
                newkey = os.path.join(os.path.dirname(key), newname).replace("\\", "/")
                
                mapping.append({"from": key, "to": newkey})
                idx += 1
            
            if dry_run:
                result = {"dryRun": True, "mapping": mapping}
                self.update_job_status(task_id, JobStatus.COMPLETED, result=result)
                return result
            
            # Execute renames using storage manager
            s3_client = self.storage.s3_client
            
            for rename_op in mapping:
                try:
                    # Copy object to new key
                    copy_source = {"Bucket": self.config.storage.out_bucket, "Key": rename_op["from"]}
                    s3_client.copy(copy_source, self.config.storage.out_bucket, rename_op["to"])
                    
                    # Delete old key
                    s3_client.delete_object(Bucket=self.config.storage.out_bucket, Key=rename_op["from"])
                    
                    logger.info(f"Renamed {rename_op['from']} -> {rename_op['to']}")
                    
                except Exception as e:
                    logger.error(f"Failed to rename {rename_op['from']}: {e}")
                    # Continue with other renames
            
            result = {"dryRun": False, "mapping": mapping}
            self.update_job_status(task_id, JobStatus.COMPLETED, result=result)
            logger.info(f"Completed rename task {task_id}")
            return result
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Rename task {task_id} failed: {error_msg}")
            self.update_job_status(task_id, JobStatus.FAILED, error_message=error_msg)
            raise


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