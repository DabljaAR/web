use std::env;

#[derive(Debug, Clone)]
pub struct AppConfig {
    pub database_url: String,
    pub aws_endpoint_url: String,
    pub aws_access_key_id: String,
    pub aws_secret_access_key: String,
    pub aws_default_region: String,
    pub s3_media_bucket: String,
    pub port: u16,
}

impl AppConfig {
    pub fn from_env() -> Result<Self, String> {
        Ok(Self {
            database_url: env::var("DATABASE_URL")
                .map_err(|_| "DATABASE_URL must be set".to_string())?,
            aws_endpoint_url: env::var("AWS_ENDPOINT_URL")
                .unwrap_or_else(|_| "http://localhost:9000".to_string()),
            aws_access_key_id: env::var("AWS_ACCESS_KEY_ID")
                .unwrap_or_else(|_| "minioadmin".to_string()),
            aws_secret_access_key: env::var("AWS_SECRET_ACCESS_KEY")
                .unwrap_or_else(|_| "minioadmin".to_string()),
            aws_default_region: env::var("AWS_DEFAULT_REGION")
                .unwrap_or_else(|_| "us-east-1".to_string()),
            s3_media_bucket: env::var("S3_MEDIA_BUCKET")
                .unwrap_or_else(|_| "dablaja-videos".to_string()),
            port: env::var("PORT")
                .unwrap_or_else(|_| "8001".to_string())
                .parse::<u16>()
                .map_err(|_| "PORT must be a valid u16".to_string())?,
        })
    }
}

#[cfg(test)]
mod tests;
