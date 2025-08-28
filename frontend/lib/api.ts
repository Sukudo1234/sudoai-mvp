/**
 * API client for sudo.ai MVP with dual-mode support
 * Handles both local (tusd) and production (S3 multipart) uploads
 */

export interface UploadInfo {
  method: 'tus' | 's3_multipart';
  endpoint: string;
  headers?: Record<string, string>;
  metadata?: {
    max_size: number;
    chunk_size: number;
    max_concurrent_uploads?: number;
    protocols: string[];
    transfer_acceleration?: boolean;
  };
  multipart_supported?: boolean;
}

export interface Job {
  id?: string;
  task_id: string;
  job_type?: string;
  status?: string;
  state: string;
  result?: any;
  error?: string;
  error_message?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  retry_count?: number;
}

export interface JobListResponse {
  jobs: Job[];
  pagination: {
    limit: number;
    offset: number;
    total: number;
  };
  stats: Record<string, number>;
}

export interface MultipartUploadInfo {
  upload_id: string;
  key: string;
  presigned_urls: Array<{
    part_number: number;
    url: string;
    size: number;
  }>;
  complete_url: string;
  abort_url: string;
  metadata?: {
    chunk_size: number;
    max_concurrent: number;
  };
}

class APIClient {
  private baseURL: string;

  constructor() {
    // Use environment variable for backend URL
    this.baseURL = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseURL}${endpoint}`;
    
    const config: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    };

    const response = await fetch(url, config);
    
    if (!response.ok) {
      const errorText = await response.text();
      let errorMessage;
      
      try {
        const errorJson = JSON.parse(errorText);
        errorMessage = errorJson.detail || errorText;
      } catch {
        errorMessage = errorText || `HTTP ${response.status}`;
      }
      
      throw new Error(`API Error: ${errorMessage}`);
    }

    // Handle empty responses
    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  }

  // ===== SYSTEM ENDPOINTS =====

  async getHealth(): Promise<any> {
    return this.request('/health');
  }

  // ===== UPLOAD ENDPOINTS =====

  async getUploadInfo(): Promise<UploadInfo> {
    return this.request('/uploads/tus');
  }

  async initiateMultipartUpload(
    filename: string,
    fileSize: number,
    contentType?: string
  ): Promise<MultipartUploadInfo> {
    return this.request('/uploads/s3/initiate', {
      method: 'POST',
      body: JSON.stringify({
        filename,
        file_size: fileSize,
        content_type: contentType,
      }),
    });
  }

  async completeMultipartUpload(
    key: string,
    uploadId: string,
    parts: Array<{ part_number: number; etag: string }>
  ): Promise<any> {
    return this.request('/uploads/s3/complete', {
      method: 'POST',
      body: JSON.stringify({
        key,
        upload_id: uploadId,
        parts,
      }),
    });
  }

  async abortMultipartUpload(key: string, uploadId: string): Promise<void> {
    return this.request(`/uploads/s3/abort?key=${key}&upload_id=${uploadId}`, {
      method: 'POST',
    });
  }

  // ===== JOB ENDPOINTS =====

  async submitSplitJob(tusUrl: string): Promise<{ task_id: string }> {
    return this.request('/split', {
      method: 'POST',
      body: JSON.stringify({ tus_url: tusUrl }),
    });
  }

  async submitMergeJob(
    videoUrl: string,
    audioUrl: string,
    offsetSec: number = 0
  ): Promise<{ task_id: string }> {
    return this.request('/merge', {
      method: 'POST',
      body: JSON.stringify({
        video_tus_url: videoUrl,
        audio_tus_url: audioUrl,
        offset_sec: offsetSec,
      }),
    });
  }

  async submitTranscribeJob(
    tusUrl: string,
    targetLanguages: string[] = ['original']
  ): Promise<{ task_id: string }> {
    return this.request('/transcribe', {
      method: 'POST',
      body: JSON.stringify({
        tus_url: tusUrl,
        target_languages: targetLanguages,
      }),
    });
  }

  async submitRenameJob(
    keys: string[],
    pattern: string,
    startIndex: number = 1,
    pad: number = 2,
    dryRun: boolean = false
  ): Promise<{ task_id: string }> {
    return this.request('/rename', {
      method: 'POST',
      body: JSON.stringify({
        keys,
        pattern,
        start_index: startIndex,
        pad,
        dryRun,
      }),
    });
  }

  async getJob(taskId: string): Promise<Job> {
    return this.request(`/jobs/${taskId}`);
  }

  async getJobs(
    status?: string,
    jobType?: string,
    limit: number = 50,
    offset: number = 0
  ): Promise<JobListResponse> {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (jobType) params.append('job_type', jobType);
    params.append('limit', limit.toString());
    params.append('offset', offset.toString());

    return this.request(`/jobs?${params.toString()}`);
  }

  async requeueJob(taskId: string): Promise<{ original_task_id: string; new_task_id: string }> {
    return this.request(`/admin/requeue/${taskId}`, {
      method: 'POST',
    });
  }

  async getSystemStats(): Promise<any> {
    return this.request('/admin/stats');
  }

  // ===== UTILITY METHODS =====

  async uploadWithTUS(file: File, uploadInfo: UploadInfo, onProgress?: (progress: number) => void): Promise<string> {
    if (typeof window === 'undefined') {
      throw new Error('TUS upload only available in browser');
    }

    // Dynamic import for TUS (client-side only)
    const tus = await import('tus-js-client');
    
    return new Promise((resolve, reject) => {
      const upload = new tus.Upload(file, {
        endpoint: uploadInfo.endpoint,
        retryDelays: [0, 3000, 5000, 10000, 20000],
        metadata: {
          filename: file.name,
          filetype: file.type,
        },
        onError: (error) => {
          reject(new Error(`Upload failed: ${error}`));
        },
        onProgress: (bytesUploaded, bytesTotal) => {
          const progress = (bytesUploaded / bytesTotal) * 100;
          onProgress?.(progress);
        },
        onSuccess: () => {
          if (upload.url) {
            resolve(upload.url);
          } else {
            reject(new Error('Upload completed but no URL returned'));
          }
        },
      });

      upload.start();
    });
  }

  async uploadWithS3Multipart(
    file: File,
    onProgress?: (progress: number) => void,
    onPartProgress?: (partNumber: number, progress: number) => void
  ): Promise<string> {
    try {
      // Initiate multipart upload
      const uploadInfo = await this.initiateMultipartUpload(
        file.name,
        file.size,
        file.type
      );

      const { presigned_urls, upload_id, key, complete_url } = uploadInfo;
      const chunkSize = uploadInfo.metadata?.chunk_size || 64 * 1024 * 1024; // 64MB default
      const maxConcurrent = uploadInfo.metadata?.max_concurrent || 3;

      // Upload parts with concurrency control
      const parts: Array<{ part_number: number; etag: string }> = [];
      let completedBytes = 0;

      // Create semaphore for concurrency control
      const semaphore = new Array(maxConcurrent).fill(null);
      
      const uploadPart = async (partInfo: typeof presigned_urls[0]): Promise<void> => {
        const { part_number, url, size } = partInfo;
        const start = (part_number - 1) * chunkSize;
        const end = Math.min(start + size, file.size);
        const chunk = file.slice(start, end);

        const response = await fetch(url, {
          method: 'PUT',
          body: chunk,
          headers: {
            'Content-Type': file.type,
          },
        });

        if (!response.ok) {
          throw new Error(`Part ${part_number} upload failed: ${response.statusText}`);
        }

        const etag = response.headers.get('ETag');
        if (!etag) {
          throw new Error(`No ETag returned for part ${part_number}`);
        }

        parts[part_number - 1] = { part_number, etag };
        completedBytes += chunk.size;

        onPartProgress?.(part_number, 100);
        onProgress?.((completedBytes / file.size) * 100);
      };

      // Upload parts with concurrency control
      const uploadPromises: Promise<void>[] = [];
      
      for (let i = 0; i < presigned_urls.length; i += maxConcurrent) {
        const batch = presigned_urls.slice(i, i + maxConcurrent);
        const batchPromises = batch.map(uploadPart);
        uploadPromises.push(...batchPromises);
        
        // Wait for current batch to complete before starting next batch
        await Promise.all(batchPromises);
      }

      await Promise.all(uploadPromises);

      // Complete multipart upload
      await this.completeMultipartUpload(key, upload_id, parts);

      // Return S3 URL for processing
      return `s3://${key.split('/')[0]}/${key}`;

    } catch (error) {
      console.error('S3 multipart upload failed:', error);
      throw error;
    }
  }
}

export const api = new APIClient();
export default api;