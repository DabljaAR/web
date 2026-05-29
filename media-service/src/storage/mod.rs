use anyhow::Result;
use async_trait::async_trait;
use aws_config::{BehaviorVersion, Region};
use aws_sdk_s3::config::Builder as S3ConfigBuilder;
use aws_sdk_s3::primitives::ByteStream;
use aws_sdk_s3::presigning::PresigningConfig;
use aws_sdk_s3::types::{Delete, ObjectIdentifier};
use aws_sdk_s3::Client as S3Client;
use std::path::Path;
use std::time::Duration;

use crate::config::AppConfig;

#[async_trait]
pub trait StorageBackend: Send + Sync {
    async fn upload_file(&self, local_path: &Path, key: &str, content_type: &str) -> Result<String>;
    async fn download_file(&self, key: &str, local_path: &Path) -> Result<bool>;
    async fn delete_object(&self, key: &str) -> Result<bool>;
    async fn delete_prefix(&self, prefix: &str) -> Result<u64>;
    async fn get_presigned_url(
        &self,
        key: &str,
        expires_secs: u64,
        method: PresignMethod,
        content_type: Option<&str>,
    ) -> Result<String>;
}

#[derive(Debug, Clone, Copy)]
pub enum PresignMethod {
    Get,
    Put,
}

pub struct S3Storage {
    client: S3Client,
    bucket: String,
}

impl S3Storage {
    pub async fn new(cfg: &AppConfig) -> Result<Self> {
        std::env::set_var("AWS_ENDPOINT_URL", &cfg.aws_endpoint_url);
        std::env::set_var("AWS_ACCESS_KEY_ID", &cfg.aws_access_key_id);
        std::env::set_var("AWS_SECRET_ACCESS_KEY", &cfg.aws_secret_access_key);
        std::env::set_var("AWS_DEFAULT_REGION", &cfg.aws_default_region);

        let sdk_config = aws_config::defaults(BehaviorVersion::latest())
            .region(Region::new(cfg.aws_default_region.clone()))
            .load()
            .await;

        let s3_cfg = S3ConfigBuilder::from(&sdk_config)
            .endpoint_url(&cfg.aws_endpoint_url)
            .force_path_style(true)
            .build();

        let client = S3Client::from_conf(s3_cfg);
        let bucket = cfg.s3_media_bucket.clone();

        match client.head_bucket().bucket(&bucket).send().await {
            Ok(_) => tracing::info!("S3Storage: bucket '{}' found.", bucket),
            Err(_) => {
                tracing::warn!("S3Storage: bucket '{}' not found, creating...", bucket);
                client
                    .create_bucket()
                    .bucket(&bucket)
                    .send()
                    .await
                    .map_err(|e| anyhow::anyhow!("Failed to create bucket '{}': {}", bucket, e))?;
                tracing::info!("S3Storage: bucket '{}' created.", bucket);
            }
        }

        Ok(Self { client, bucket })
    }
}

#[async_trait]
impl StorageBackend for S3Storage {
    async fn upload_file(&self, local_path: &Path, key: &str, content_type: &str) -> Result<String> {
        let body = ByteStream::from_path(local_path)
            .await
            .map_err(|e| anyhow::anyhow!("Failed to read file {:?}: {}", local_path, e))?;

        self.client
            .put_object()
            .bucket(&self.bucket)
            .key(key)
            .content_type(content_type)
            .body(body)
            .send()
            .await
            .map_err(|e| anyhow::anyhow!("S3 put_object failed for key '{}': {}", key, e))?;

        tracing::info!("S3Storage: uploaded {:?} → {}", local_path, key);
        Ok(key.to_string())
    }

    async fn download_file(&self, key: &str, local_path: &Path) -> Result<bool> {
        let resp = match self.client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
        {
            Ok(r) => r,
            Err(e) => {
                tracing::error!("S3 get_object failed for key '{}': {}", key, e);
                return Ok(false);
            }
        };

        if let Some(parent) = local_path.parent() {
            tokio::fs::create_dir_all(parent).await
                .map_err(|e| anyhow::anyhow!("Failed to create dir {:?}: {}", parent, e))?;
        }

        let data = resp.body.collect().await
            .map_err(|e| anyhow::anyhow!("Failed to read S3 body for '{}': {}", key, e))?;

        tokio::fs::write(local_path, data.into_bytes()).await
            .map_err(|e| anyhow::anyhow!("Failed to write file {:?}: {}", local_path, e))?;

        tracing::info!("S3Storage: downloaded {} → {:?}", key, local_path);
        Ok(true)
    }

    async fn delete_object(&self, key: &str) -> Result<bool> {
        self.client
            .delete_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
            .map_err(|e| anyhow::anyhow!("S3 delete_object failed for key '{}': {}", key, e))?;
        Ok(true)
    }

    async fn delete_prefix(&self, prefix: &str) -> Result<u64> {
        let mut total_deleted = 0u64;
        let mut continuation: Option<String> = None;

        loop {
            let mut req = self
                .client
                .list_objects_v2()
                .bucket(&self.bucket)
                .prefix(prefix);

            if let Some(token) = continuation.as_ref() {
                req = req.continuation_token(token);
            }

            let resp = req
                .send()
                .await
                .map_err(|e| anyhow::anyhow!("S3 list_objects_v2 failed for prefix '{}': {}", prefix, e))?;

            let mut objects: Vec<ObjectIdentifier> = Vec::new();
            for obj in resp.contents() {
                if let Some(key) = obj.key() {
                    if let Ok(oid) = ObjectIdentifier::builder().key(key).build() {
                        objects.push(oid);
                    }
                }
            }

            if !objects.is_empty() {
                let delete = Delete::builder()
                    .set_objects(Some(objects))
                    .build()
                    .map_err(|e| anyhow::anyhow!("Failed to build Delete request: {}", e))?;
                let result = self
                    .client
                    .delete_objects()
                    .bucket(&self.bucket)
                    .delete(delete)
                    .send()
                    .await
                    .map_err(|e| anyhow::anyhow!("S3 delete_objects failed for prefix '{}': {}", prefix, e))?;

                total_deleted += result.deleted().len() as u64;
            }

            if resp.is_truncated().unwrap_or(false) {
                continuation = resp.next_continuation_token().map(|s| s.to_string());
            } else {
                break;
            }
        }

        Ok(total_deleted)
    }

    async fn get_presigned_url(
        &self,
        key: &str,
        expires_secs: u64,
        method: PresignMethod,
        content_type: Option<&str>,
    ) -> Result<String> {
        let presign_cfg = PresigningConfig::expires_in(Duration::from_secs(expires_secs))
            .map_err(|e| anyhow::anyhow!("Failed to build presigning config: {}", e))?;

        let presigned = match method {
            PresignMethod::Get => self
                .client
                .get_object()
                .bucket(&self.bucket)
                .key(key)
                .presigned(presign_cfg)
                .await
                .map_err(|e| anyhow::anyhow!("Failed to generate presigned GET for '{}': {}", key, e))?,
            PresignMethod::Put => {
                let mut req = self.client.put_object().bucket(&self.bucket).key(key);
                if let Some(ct) = content_type {
                    req = req.content_type(ct);
                }
                req.presigned(presign_cfg)
                    .await
                    .map_err(|e| anyhow::anyhow!("Failed to generate presigned PUT for '{}': {}", key, e))?
            }
        };

        Ok(presigned.uri().to_string())
    }
}
