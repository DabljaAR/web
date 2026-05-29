use axum::http::StatusCode;
use crate::routes::health::health_check;

#[tokio::test]
async fn test_health_check_returns_200_ok() {
    let (status, axum::response::Json(body)) = health_check().await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "ok");
}

#[tokio::test]
async fn test_health_check_body_is_valid_json_object() {
    let (_, axum::response::Json(body)) = health_check().await;
    assert!(body.is_object());
}

#[tokio::test]
async fn test_health_check_has_exactly_one_field() {
    let (_, axum::response::Json(body)) = health_check().await;
    let obj = body.as_object().unwrap();
    assert_eq!(obj.len(), 1, "response should have exactly one field");
    assert!(obj.contains_key("status"));
}

#[tokio::test]
async fn test_health_check_status_value_is_string_ok() {
    let (_, axum::response::Json(body)) = health_check().await;
    assert_eq!(body["status"].as_str(), Some("ok"));
}
