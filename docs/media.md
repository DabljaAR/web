# Media Service

The media layer handles upload, storage, and background processing of video/audio assets.

## Responsibilities

- Secure media upload APIs
- Storage abstraction for local filesystem and S3-compatible object storage
- Async processing via Celery workers
- FFmpeg-based metadata extraction and media transforms
- Automatic cleanup of related assets when video records are removed

## Why Object Storage (MinIO/S3)

Media workloads are write-once/read-many and file-size heavy. Object storage is preferred because it:

- Scales better for large unstructured files
- Provides simple HTTP access patterns
- Aligns with cloud-native storage APIs
- Keeps application services decoupled from physical disk layout

## Storage Compatibility

The backend uses S3-compatible clients (`aioboto3`). This allows seamless migration between MinIO and AWS S3 through configuration changes instead of code rewrites.

## Processing Flow

```text
Upload -> Persist metadata -> Enqueue media job
      -> FFmpeg probe (duration, codec, dimensions)
      -> Extract audio track
      -> Generate thumbnail
      -> Update job/video status
```

## Operational Notes

- Keep worker images provisioned with `ffmpeg`
- Verify bucket permissions and endpoint config in env
- Use background queues for heavy transforms to keep API response times low
