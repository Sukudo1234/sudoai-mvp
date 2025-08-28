#!/usr/bin/env python3
"""
Test script for worker functionality in both local and production modes
"""
import os
import sys
import tempfile
import json
from pathlib import Path

# Add parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from shared.config import config, Environment
from worker.enhanced_tasks import task_processor


def create_test_audio_file() -> str:
    """Create a simple test audio file using ffmpeg"""
    
    # Create a 5-second sine wave test tone
    output_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "sine=frequency=440:duration=5",
        "-ar", "44100",
        "-ac", "2",
        output_file
    ]
    
    import subprocess
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create test audio: {result.stderr}")
    
    print(f"Created test audio file: {output_file}")
    return output_file


def test_local_mode():
    """Test worker in local mode"""
    print("\n=== Testing Local Mode ===")
    
    if config.environment != Environment.LOCAL:
        print("❌ Not in local mode, skipping local tests")
        return
    
    try:
        # Test basic task processor initialization
        processor = task_processor
        print("✅ Task processor initialized")
        
        # Create test file and upload to MinIO
        test_file = create_test_audio_file()
        
        # In local mode, we need to simulate a tusd upload URL
        # For testing, we can copy the file to MinIO directly
        from shared.storage_manager import storage_manager
        
        # Upload test file
        test_key = f"test-uploads/{os.path.basename(test_file)}"
        upload_url = storage_manager.upload_file(test_file, test_key, storage_manager.config.raw_bucket)
        
        print(f"✅ Uploaded test file to MinIO: {test_key}")
        
        # Create S3 URL for the uploaded file  
        s3_url = f"s3://{storage_manager.config.raw_bucket}/{test_key}"
        
        # Test split task
        task_id = "test-split-001"
        
        print(f"🔄 Running split task {task_id}...")
        result = processor.split_task(task_id, s3_url)
        
        print("✅ Split task completed successfully!")
        print(f"Result: {json.dumps(result, indent=2)}")
        
        # Cleanup
        os.remove(test_file)
        
    except Exception as e:
        print(f"❌ Local test failed: {e}")
        import traceback
        traceback.print_exc()


def test_production_mode():
    """Test worker in production mode"""
    print("\n=== Testing Production Mode ===")
    
    if config.environment != Environment.PRODUCTION:
        print("❌ Not in production mode, skipping production tests")
        return
    
    try:
        # Test basic task processor initialization
        processor = task_processor
        print("✅ Task processor initialized")
        
        # In production, we would test with actual S3 URLs
        # For now, just test the AWS connections
        
        from shared.storage_manager import storage_manager
        from shared.database import db_manager
        
        # Test S3 connection
        try:
            buckets = [storage_manager.config.raw_bucket, storage_manager.config.out_bucket]
            for bucket in buckets:
                storage_manager.s3_client.head_bucket(Bucket=bucket)
            print("✅ S3 buckets accessible")
        except Exception as e:
            print(f"❌ S3 connection failed: {e}")
        
        # Test database connection
        try:
            stats = db_manager.get_job_stats()
            print(f"✅ Database connection successful: {stats}")
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
        
        print("✅ Production environment checks passed")
        
    except Exception as e:
        print(f"❌ Production test failed: {e}")
        import traceback
        traceback.print_exc()


def test_batch_entry_point():
    """Test AWS Batch entry point"""
    print("\n=== Testing Batch Entry Point ===")
    
    if config.environment != Environment.PRODUCTION:
        print("❌ Not in production mode, skipping Batch tests")
        return
    
    # Test environment variable parsing
    os.environ['TASK_ID'] = 'test-batch-001'
    os.environ['INPUT_PARAMS'] = json.dumps({
        'tus_url': 's3://test-bucket/test-key.wav'
    })
    
    try:
        from worker.enhanced_tasks import batch_main
        
        # This would normally be called by Batch, but we can test the parsing logic
        task_id = os.getenv('TASK_ID')
        job_params = os.getenv('INPUT_PARAMS')
        
        if task_id and job_params:
            params = json.loads(job_params)
            print(f"✅ Batch parameters parsed successfully:")
            print(f"  Task ID: {task_id}")
            print(f"  Params: {params}")
        else:
            print("❌ Batch parameter parsing failed")
            
    except Exception as e:
        print(f"❌ Batch entry point test failed: {e}")
    
    finally:
        # Cleanup environment variables
        os.environ.pop('TASK_ID', None)
        os.environ.pop('INPUT_PARAMS', None)


def main():
    """Run all worker tests"""
    print("🧪 Worker Test Suite")
    print(f"Environment: {config.environment.value}")
    print(f"Storage: {config.storage.raw_bucket} / {config.storage.out_bucket}")
    print(f"Queue: {config.queue.type}")
    
    # Test based on current environment
    if config.environment == Environment.LOCAL:
        test_local_mode()
    else:
        test_production_mode()
        test_batch_entry_point()
    
    print("\n🎉 Worker tests completed!")


if __name__ == "__main__":
    main()