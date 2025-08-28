#!/usr/bin/env python3
"""
Worker startup script for both local (Celery) and production (Batch) modes
"""
import os
import sys
import subprocess
from pathlib import Path

# Add parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from shared.config import config, Environment


def run_celery_worker():
    """Run Celery worker for local development"""
    print("🚀 Starting Celery worker for local development...")
    
    # Change to worker directory
    worker_dir = Path(__file__).parent.parent / "worker"
    os.chdir(worker_dir)
    
    # Run Celery worker
    cmd = [
        "celery", "-A", "enhanced_tasks.celery_app", "worker",
        "--loglevel=info",
        "--concurrency=2",
        "--pool=threads"  # Use threads for better compatibility
    ]
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n👋 Celery worker stopped")
    except subprocess.CalledProcessError as e:
        print(f"❌ Celery worker failed: {e}")
        sys.exit(1)


def run_batch_worker():
    """Information for running in AWS Batch"""
    print("📋 AWS Batch Worker Configuration")
    print("\nThis worker is designed to run in AWS Batch.")
    print("To deploy:")
    print("1. Build and push Docker image to ECR")
    print("2. Update Batch job definitions with new image")
    print("3. Submit jobs through the API")
    print("\nFor local testing of Batch entry point:")
    print("  ENVIRONMENT=production TASK_ID=test-001 INPUT_PARAMS='{\"tus_url\":\"s3://bucket/key\"}' python enhanced_tasks.py split")


def show_help():
    """Show usage information"""
    print("Worker Management Script")
    print("\nUsage:")
    print("  python run-worker.py [command]")
    print("\nCommands:")
    print("  start    - Start worker (auto-detects environment)")
    print("  celery   - Force start Celery worker (local mode)")
    print("  batch    - Show Batch worker info (production mode)")
    print("  test     - Run worker tests")
    print("  help     - Show this help message")


def run_tests():
    """Run worker tests"""
    print("🧪 Running worker tests...")
    
    test_script = Path(__file__).parent / "test-worker.py"
    
    try:
        subprocess.run(["python", str(test_script)], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Tests failed: {e}")
        sys.exit(1)


def main():
    """Main entry point"""
    
    # Parse command line arguments
    command = sys.argv[1] if len(sys.argv) > 1 else "start"
    
    if command in ["help", "-h", "--help"]:
        show_help()
        return
    
    print(f"🔧 Environment: {config.environment.value}")
    print(f"📦 Storage: {config.storage.raw_bucket}")
    print(f"🔄 Queue: {config.queue.type}")
    
    if command == "start":
        # Auto-detect based on environment
        if config.environment == Environment.LOCAL:
            run_celery_worker()
        else:
            run_batch_worker()
    elif command == "celery":
        run_celery_worker()
    elif command == "batch":
        run_batch_worker()
    elif command == "test":
        run_tests()
    else:
        print(f"❌ Unknown command: {command}")
        show_help()
        sys.exit(1)


if __name__ == "__main__":
    main()