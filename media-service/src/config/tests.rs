use super::AppConfig;
use std::env;
use std::sync::Mutex;

// Serialize env-var tests so parallel test threads don't race each other.
static ENV_LOCK: Mutex<()> = Mutex::new(());

fn clear_env() {
    for key in &[
        "DATABASE_URL",
        "AWS_ENDPOINT_URL",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
        "S3_MEDIA_BUCKET",
        "PORT",
    ] {
        env::remove_var(key);
    }
}

// ── Required field ───────────────────────────────────────────────────────────

#[test]
fn test_missing_database_url_returns_error() {
    let _g = ENV_LOCK.lock().unwrap();
    clear_env();
    let err = AppConfig::from_env().unwrap_err();
    assert!(err.contains("DATABASE_URL"), "error should mention DATABASE_URL, got: {err}");
}

// ── Defaults ─────────────────────────────────────────────────────────────────

#[test]
fn test_optional_fields_use_defaults_when_unset() {
    let _g = ENV_LOCK.lock().unwrap();
    clear_env();
    env::set_var("DATABASE_URL", "postgres://test@localhost/testdb");

    let cfg = AppConfig::from_env().unwrap();
    assert_eq!(cfg.aws_endpoint_url, "http://localhost:9000");
    assert_eq!(cfg.aws_access_key_id, "minioadmin");
    assert_eq!(cfg.aws_secret_access_key, "minioadmin");
    assert_eq!(cfg.aws_default_region, "us-east-1");
    assert_eq!(cfg.s3_media_bucket, "dablaja-videos");
    assert_eq!(cfg.port, 8001);
}

#[test]
fn test_database_url_is_preserved_exactly() {
    let _g = ENV_LOCK.lock().unwrap();
    clear_env();
    let url = "postgres://user:s3cr3t@db.internal:5432/prod_db";
    env::set_var("DATABASE_URL", url);

    let cfg = AppConfig::from_env().unwrap();
    assert_eq!(cfg.database_url, url);
}

// ── All vars explicitly set ──────────────────────────────────────────────────

#[test]
fn test_all_env_vars_override_defaults() {
    let _g = ENV_LOCK.lock().unwrap();
    clear_env();
    env::set_var("DATABASE_URL", "postgres://user:pass@db/prod");
    env::set_var("AWS_ENDPOINT_URL", "https://s3.amazonaws.com");
    env::set_var("AWS_ACCESS_KEY_ID", "AKIAIOSFODNN7EXAMPLE");
    env::set_var("AWS_SECRET_ACCESS_KEY", "wJalrXUtnFEMI/K7MDENG");
    env::set_var("AWS_DEFAULT_REGION", "eu-west-1");
    env::set_var("S3_MEDIA_BUCKET", "my-prod-bucket");
    env::set_var("PORT", "9090");

    let cfg = AppConfig::from_env().unwrap();
    assert_eq!(cfg.database_url, "postgres://user:pass@db/prod");
    assert_eq!(cfg.aws_endpoint_url, "https://s3.amazonaws.com");
    assert_eq!(cfg.aws_access_key_id, "AKIAIOSFODNN7EXAMPLE");
    assert_eq!(cfg.aws_secret_access_key, "wJalrXUtnFEMI/K7MDENG");
    assert_eq!(cfg.aws_default_region, "eu-west-1");
    assert_eq!(cfg.s3_media_bucket, "my-prod-bucket");
    assert_eq!(cfg.port, 9090);
}

// ── PORT validation ──────────────────────────────────────────────────────────

#[test]
fn test_invalid_port_string_returns_error() {
    let _g = ENV_LOCK.lock().unwrap();
    clear_env();
    env::set_var("DATABASE_URL", "postgres://test@localhost/testdb");
    env::set_var("PORT", "not-a-number");

    let err = AppConfig::from_env().unwrap_err();
    assert!(err.contains("PORT"), "error should mention PORT, got: {err}");
}

#[test]
fn test_port_above_u16_max_returns_error() {
    let _g = ENV_LOCK.lock().unwrap();
    clear_env();
    env::set_var("DATABASE_URL", "postgres://test@localhost/testdb");
    env::set_var("PORT", "65536"); // u16::MAX is 65535

    assert!(AppConfig::from_env().is_err());
}

#[test]
fn test_negative_port_string_returns_error() {
    let _g = ENV_LOCK.lock().unwrap();
    clear_env();
    env::set_var("DATABASE_URL", "postgres://test@localhost/testdb");
    env::set_var("PORT", "-1");

    assert!(AppConfig::from_env().is_err());
}

#[test]
fn test_port_zero_is_accepted() {
    let _g = ENV_LOCK.lock().unwrap();
    clear_env();
    env::set_var("DATABASE_URL", "postgres://test@localhost/testdb");
    env::set_var("PORT", "0");

    let cfg = AppConfig::from_env().unwrap();
    assert_eq!(cfg.port, 0);
}

#[test]
fn test_port_max_u16_is_accepted() {
    let _g = ENV_LOCK.lock().unwrap();
    clear_env();
    env::set_var("DATABASE_URL", "postgres://test@localhost/testdb");
    env::set_var("PORT", "65535");

    let cfg = AppConfig::from_env().unwrap();
    assert_eq!(cfg.port, 65535);
}

// ── Clone ────────────────────────────────────────────────────────────────────

#[test]
fn test_config_clone_produces_independent_copy() {
    let _g = ENV_LOCK.lock().unwrap();
    clear_env();
    env::set_var("DATABASE_URL", "postgres://test@localhost/testdb");
    env::set_var("PORT", "3000");

    let original = AppConfig::from_env().unwrap();
    let cloned = original.clone();
    assert_eq!(original.database_url, cloned.database_url);
    assert_eq!(original.port, cloned.port);
    assert_eq!(original.s3_media_bucket, cloned.s3_media_bucket);
}
