# DabljaAR API Documentation

## Base URL
```
Production: https://api.dabljaar.com
Development: http://localhost:8000
```

## API Version
Current version: `v1`

All endpoints are prefixed with `/api/v1`

---

## Table of Contents
- [Authentication](#authentication)
- [User Management](#user-management)
- [Subscription Management](#subscription-management)
- [Payment Management](#payment-management)
- [Voice Management](#voice-management)
- [Domain Management](#domain-management)
- [Media Input Management](#media-input-management)
- [Task Management](#task-management)
- [Output Management](#output-management)
- [Error Codes](#error-codes)

---

## Authentication

### Register New User
**POST** `/api/v1/auth/signup`

Register a new user account.

**Request Body:**
```json
{
  "username": "john_doe",
  "email": "john@example.com",
  "password": "SecurePass123!",
  "first_name": "John",
  "last_name": "Doe",
  "preferred_language": "EN"
}
```

**Response:** `201 Created`
```json
{
  "user_id": 1,
  "username": "john_doe",
  "email": "john@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "preferred_language": "EN",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error Responses:**
- `400 Bad Request` - Invalid input data
- `409 Conflict` - Username or email already exists

---
### User Login
**POST** `/api/v1/auth/login`

Authenticate user and receive JWT tokens.

**Request Body:**
```json
{
  "email": "john@example.com",
  "password": "SecurePass123!"
}
```

**Response:** `200 OK`
```json
{
  "user_id": 1,
  "username": "john_doe",
  "email": "john@example.com",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error Responses:**
- `401 Unauthorized` - Invalid credentials
- `403 Forbidden` - Account is not active

---

### Refresh Access Token
**POST** `/api/v1/auth/refresh`

Get a new access token using a refresh token.

**Request Body:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response:** `200 OK`
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error Responses:**
- `401 Unauthorized` - Invalid or expired refresh token

---

### Logout
**POST** `/api/v1/auth/logout`

Invalidate the current refresh token.

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:** `204 No Content`

---

### Request Password Reset
**POST** `/api/v1/auth/request-password-reset`

Request a password reset email.

**Request Body:**
```json
{
  "email": "john@example.com"
}
```

**Response:** `200 OK`
```json
{
  "message": "Password reset email sent if account exists"
}
```

---

### Reset Password
**POST** `/api/v1/auth/reset-password`

Reset password using reset token.

**Request Body:**
```json
{
  "token": "reset_token_from_email",
  "new_password": "NewSecurePass123!"
}
```

**Response:** `200 OK`
```json
{
  "message": "Password successfully reset"
}
```

**Error Responses:**
- `400 Bad Request` - Invalid or expired token

---

## User Management

All user management endpoints require authentication.

**Headers for all endpoints:**
```
Authorization: Bearer <access_token>
```

---

### Get Current User Profile
**GET** `/api/v1/users/me`

Get the authenticated user's profile.

**Response:** `200 OK`
```json
{
  "user_id": 1,
  "username": "john_doe",
  "email": "john@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "preferred_language": "EN",
  "avatar_url": "https://storage.dabljaar.com/avatars/john_doe.jpg",
  "is_active": true,
  "created_at": "2025-01-01T10:00:00Z",
  "updated_at": "2025-01-15T14:30:00Z",
  "last_login": "2025-12-24T08:00:00Z"
}
```

---

### Update User Profile
**PUT** `/api/v1/users/me`

Update the authenticated user's profile.

**Request Body:**
```json
{
  "first_name": "John",
  "last_name": "Smith",
  "preferred_language": "AR"
}
```

**Response:** `200 OK`
```json
{
  "user_id": 1,
  "username": "john_doe",
  "email": "john@example.com",
  "first_name": "John",
  "last_name": "Smith",
  "preferred_language": "AR",
  "avatar_url": "https://storage.dabljaar.com/avatars/john_doe.jpg",
  "updated_at": "2025-12-24T09:00:00Z"
}
```

---

### Upload Avatar
**PATCH** `/api/v1/users/me/avatar`

Upload a new avatar image.

**Request:** `multipart/form-data`
```
avatar: <file> (JPEG, PNG, max 5MB)
```

**Response:** `200 OK`
```json
{
  "avatar_url": "https://storage.dabljaar.com/avatars/john_doe_new.jpg",
  "updated_at": "2025-12-24T09:15:00Z"
}
```

**Error Responses:**
- `400 Bad Request` - Invalid file format or size
- `413 Payload Too Large` - File exceeds 5MB

---

### Change Password
**PATCH** `/api/v1/users/me/password`

Change the user's password.

**Request Body:**
```json
{
  "current_password": "OldPassword123!",
  "new_password": "NewSecurePass123!"
}
```

**Response:** `200 OK`
```json
{
  "message": "Password successfully changed"
}
```

**Error Responses:**
- `401 Unauthorized` - Current password is incorrect

---

### Delete User Account
**DELETE** `/api/v1/users/me`

Delete the authenticated user's account (soft delete).

**Response:** `204 No Content`

---

### Get User Preferences
**GET** `/api/v1/users/me/preferences`

Get user preferences and settings.

**Response:** `200 OK`
```json
{
  "preferred_language": "EN",
  "notifications_enabled": true,
  "email_notifications": true,
  "default_voice_id": 5,
  "default_domain_id": 2
}
```

---

### Update User Preferences
**PUT** `/api/v1/users/me/preferences`

Update user preferences.

**Request Body:**
```json
{
  "preferred_language": "AR",
  "notifications_enabled": false,
  "default_voice_id": 10
}
```

**Response:** `200 OK`
```json
{
  "preferred_language": "AR",
  "notifications_enabled": false,
  "email_notifications": true,
  "default_voice_id": 10,
  "default_domain_id": 2
}
```

---

## Subscription Management

### List All Subscription Plans
**GET** `/api/v1/subscriptions/plans`

Get all available subscription plans (public endpoint).

**Query Parameters:**
- `is_active` (boolean, optional): Filter by active status

**Response:** `200 OK`
```json
{
  "plans": [
    {
      "plan_id": 1,
      "name": "Free",
      "price": 0.00,
      "description": "Basic features with limitations",
      "features": [
        "10 minutes of dubbing per month",
        "Standard voices only",
        "720p max resolution"
      ]
    },
    {
      "plan_id": 2,
      "name": "Pro",
      "price": 29.99,
      "description": "Professional features for content creators",
      "features": [
        "300 minutes of dubbing per month",
        "Premium voices",
        "4K resolution support",
        "Custom voice cloning"
      ]
    },
    {
      "plan_id": 3,
      "name": "Enterprise",
      "price": 99.99,
      "description": "Unlimited features for businesses",
      "features": [
        "Unlimited dubbing",
        "All premium voices",
        "Priority processing",
        "API access",
        "Dedicated support"
      ]
    }
  ]
}
```

---

### Get Subscription Plan Details
**GET** `/api/v1/subscriptions/plans/{plan_id}`

Get details of a specific subscription plan.

**Response:** `200 OK`
```json
{
  "plan_id": 2,
  "name": "Pro",
  "price": 29.99,
  "description": "Professional features for content creators",
  "features": [
    "300 minutes of dubbing per month",
    "Premium voices",
    "4K resolution support",
    "Custom voice cloning"
  ],
  "billing_cycle": "monthly"
}
```

---

### Subscribe to a Plan
**POST** `/api/v1/subscriptions/subscribe`

Subscribe to a plan (requires authentication).

**Request Body:**
```json
{
  "plan_id": 2,
  "payment_method": "credit_card",
  "auto_renew": true
}
```

**Response:** `201 Created`
```json
{
  "subscription_id": 1,
  "user_id": 1,
  "plan_id": 2,
  "plan_name": "Pro",
  "status": "active",
  "start_date": "2025-12-24T10:00:00Z",
  "end_date": "2026-01-24T10:00:00Z",
  "auto_renew": true,
  "payment_required": true,
  "payment_url": "https://payment.dabljaar.com/checkout/abc123"
}
```

---

### Get User Subscription
**GET** `/api/v1/users/me/subscription`

Get the authenticated user's current subscription.

**Response:** `200 OK`
```json
{
  "subscription_id": 1,
  "plan": {
    "plan_id": 2,
    "name": "Pro",
    "price": 29.99
  },
  "status": "active",
  "start_date": "2025-12-24T10:00:00Z",
  "end_date": "2026-01-24T10:00:00Z",
  "auto_renew": true,
  "usage": {
    "minutes_used": 45,
    "minutes_limit": 300,
    "tasks_completed": 12
  }
}
```

**Error Responses:**
- `404 Not Found` - User has no active subscription

---

### Cancel Subscription
**PUT** `/api/v1/users/me/subscription/cancel`

Cancel the user's subscription (effective at end of billing period).

**Response:** `200 OK`
```json
{
  "subscription_id": 1,
  "status": "cancelled",
  "end_date": "2026-01-24T10:00:00Z",
  "message": "Subscription will remain active until end date"
}
```

---

### Reactivate Subscription
**PUT** `/api/v1/users/me/subscription/reactivate`

Reactivate a cancelled subscription.

**Response:** `200 OK`
```json
{
  "subscription_id": 1,
  "status": "active",
  "auto_renew": true,
  "message": "Subscription reactivated successfully"
}
```

---

### Update Subscription Auto-Renewal
**PATCH** `/api/v1/users/me/subscription/auto-renew`

Toggle auto-renewal setting.

**Request Body:**
```json
{
  "auto_renew": false
}
```

**Response:** `200 OK`
```json
{
  "subscription_id": 1,
  "auto_renew": false,
  "message": "Auto-renewal disabled"
}
```

---

## Payment Management

### Initiate Payment
**POST** `/api/v1/payments/initiate`

Initiate a payment for subscription or credits.

**Request Body:**
```json
{
  "subscription_id": 1,
  "amount": 29.99,
  "currency": "USD",
  "payment_method": "credit_card",
  "payment_gateway": "paypal"
}
```

**Response:** `201 Created`
```json
{
  "payment_id": 1,
  "transaction_id": "TXN_ABC123XYZ",
  "amount": 29.99,
  "currency": "USD",
  "status": "pending",
  "payment_url": "https://paypal.com/checkout/abc123",
  "expires_at": "2025-12-24T11:00:00Z"
}
```

---

### Get Payment Details
**GET** `/api/v1/payments/{payment_id}`

Get details of a specific payment.

**Response:** `200 OK`
```json
{
  "payment_id": 1,
  "user_id": 1,
  "subscription_id": 1,
  "amount": 29.99,
  "currency": "USD",
  "payment_method": "credit_card",
  "payment_gateway": "paypal",
  "transaction_id": "TXN_ABC123XYZ",
  "status": "paid",
  "payment_date": "2025-12-24T10:30:00Z"
}
```

---

### List User Payments
**GET** `/api/v1/users/me/payments`

Get all payments for the authenticated user.

**Query Parameters:**
- `status` (string, optional): Filter by status (paid, pending, failed, refunded)
- `limit` (integer, default: 20): Number of results
- `offset` (integer, default: 0): Pagination offset

**Response:** `200 OK`
```json
{
  "payments": [
    {
      "payment_id": 1,
      "amount": 29.99,
      "currency": "USD",
      "status": "paid",
      "payment_date": "2025-12-24T10:30:00Z",
      "subscription": {
        "plan_name": "Pro"
      }
    },
    {
      "payment_id": 2,
      "amount": 29.99,
      "currency": "USD",
      "status": "paid",
      "payment_date": "2025-11-24T10:30:00Z",
      "subscription": {
        "plan_name": "Pro"
      }
    }
  ],
  "total": 2,
  "limit": 20,
  "offset": 0
}
```

---

### Payment Webhooks

#### Fawry Webhook
**POST** `/api/v1/webhooks/fawry`

Webhook endpoint for Fawry payment notifications (internal use).

---

#### PayPal Webhook
**POST** `/api/v1/webhooks/paypal`

Webhook endpoint for PayPal payment notifications (internal use).

---

#### Paymob Webhook
**POST** `/api/v1/webhooks/paymob`

Webhook endpoint for Paymob payment notifications (internal use).

---

## Voice Management

### List All Voices
**GET** `/api/v1/voices`

Get all available voices (system + user's custom voices).

**Query Parameters:**
- `gender` (string, optional): Filter by gender (male, female)
- `is_premium` (boolean, optional): Filter by premium status
- `language` (string, optional): Filter by language (EN, AR)
- `limit` (integer, default: 50)
- `offset` (integer, default: 0)

**Response:** `200 OK`
```json
{
  "voices": [
    {
      "voice_id": 1,
      "name": "Emma - Professional",
      "gender": "female",
      "language": "EN",
      "is_premium": false,
      "is_system": true,
      "sample_url": "https://storage.dabljaar.com/voices/samples/emma.mp3",
      "times_used": 1523
    },
    {
      "voice_id": 5,
      "name": "My Custom Voice",
      "gender": "male",
      "language": "AR",
      "is_premium": true,
      "is_system": false,
      "is_shareable": false,
      "created_at": "2025-11-15T12:00:00Z",
      "times_used": 45
    }
  ],
  "total": 25,
  "limit": 50,
  "offset": 0
}
```

---

### List System Voices
**GET** `/api/v1/voices/system`

Get all system-provided voices.

**Response:** `200 OK`
```json
{
  "voices": [
    {
      "voice_id": 1,
      "name": "Emma - Professional",
      "gender": "female",
      "language": "EN",
      "is_premium": false,
      "sample_url": "https://storage.dabljaar.com/voices/samples/emma.mp3"
    },
    {
      "voice_id": 2,
      "name": "محمد - احترافي",
      "gender": "male",
      "language": "AR",
      "is_premium": false,
      "sample_url": "https://storage.dabljaar.com/voices/samples/mohamed.mp3"
    }
  ]
}
```

---

### List User's Custom Voices
**GET** `/api/v1/voices/user`

Get authenticated user's custom cloned voices.

**Response:** `200 OK`
```json
{
  "voices": [
    {
      "voice_id": 15,
      "name": "My Voice Clone",
      "gender": "male",
      "is_premium": true,
      "is_shareable": false,
      "created_at": "2025-12-01T14:00:00Z",
      "times_used": 23
    }
  ]
}
```

---

### Clone Voice
**POST** `/api/v1/voices/clone`

Create a custom voice clone (requires premium subscription).

**Request:** `multipart/form-data`
```
name: "My Custom Voice"
audio_samples: <file[]> (Multiple audio files, WAV/MP3, 5-10 minutes total)
gender: "male"
```

**Response:** `202 Accepted`
```json
{
  "voice_id": 15,
  "name": "My Custom Voice",
  "status": "processing",
  "estimated_completion": "2025-12-24T12:00:00Z",
  "message": "Voice cloning started. You'll be notified when ready."
}
```

**Error Responses:**
- `403 Forbidden` - Premium subscription required
- `400 Bad Request` - Invalid audio samples

---

### Get Voice Details
**GET** `/api/v1/voices/{voice_id}`

Get details of a specific voice.

**Response:** `200 OK`
```json
{
  "voice_id": 1,
  "name": "Emma - Professional",
  "gender": "female",
  "language": "EN",
  "is_premium": false,
  "is_system": true,
  "sample_url": "https://storage.dabljaar.com/voices/samples/emma.mp3",
  "description": "Professional female voice with clear articulation",
  "times_used": 1523,
  "created_at": "2024-01-01T00:00:00Z"
}
```

---

### Delete Custom Voice
**DELETE** `/api/v1/voices/{voice_id}`

Delete a custom voice (user can only delete their own voices).

**Response:** `204 No Content`

**Error Responses:**
- `403 Forbidden` - Cannot delete system voices or other users' voices
- `404 Not Found` - Voice not found

---

## Domain Management

### List All Domains
**GET** `/api/v1/domains`

Get all available domains for RAG context.

**Query Parameters:**
- `is_active` (boolean, optional): Filter by active status

**Response:** `200 OK`
```json
{
  "domains": [
    {
      "domain_id": 1,
      "name": "General",
      "description": "General purpose conversations and content",
      "is_active": true,
      "last_updated": "2025-01-01T00:00:00Z"
    },
    {
      "domain_id": 2,
      "name": "Medical",
      "description": "Medical and healthcare terminology",
      "is_active": true,
      "last_updated": "2025-06-15T10:00:00Z"
    },
    {
      "domain_id": 3,
      "name": "Technical",
      "description": "Technical and software development content",
      "is_active": true,
      "last_updated": "2025-08-20T14:30:00Z"
    },
    {
      "domain_id": 4,
      "name": "Legal",
      "description": "Legal documents and terminology",
      "is_active": true,
      "last_updated": "2025-10-10T09:00:00Z"
    }
  ],
  "total": 4
}
```

---

### Get Domain Details
**GET** `/api/v1/domains/{domain_id}`

Get details of a specific domain.

**Response:** `200 OK`
```json
{
  "domain_id": 2,
  "name": "Medical",
  "description": "Medical and healthcare terminology including anatomy, procedures, and diagnoses",
  "is_active": true,
  "last_updated": "2025-06-15T10:00:00Z",
  "vocabulary_size": 15420,
  "supported_languages": ["EN", "AR"]
}
```

---

### Create Domain (Admin Only)
**POST** `/api/v1/admin/domains`

Create a new domain (requires admin privileges).

**Request Body:**
```json
{
  "name": "Finance",
  "description": "Financial and business terminology",
  "is_active": true
}
```

**Response:** `201 Created`
```json
{
  "domain_id": 5,
  "name": "Finance",
  "description": "Financial and business terminology",
  "is_active": true,
  "created_at": "2025-12-24T10:00:00Z"
}
```

---

### Update Domain (Admin Only)
**PUT** `/api/v1/admin/domains/{domain_id}`

Update an existing domain.

**Request Body:**
```json
{
  "description": "Updated description with more details",
  "is_active": true
}
```

**Response:** `200 OK`
```json
{
  "domain_id": 5,
  "name": "Finance",
  "description": "Updated description with more details",
  "is_active": true,
  "last_updated": "2025-12-24T10:15:00Z"
}
```

---

### Delete Domain (Admin Only)
**DELETE** `/api/v1/admin/domains/{domain_id}`

Delete a domain (soft delete).

**Response:** `204 No Content`

---

## Media Input Management

### Upload Video
**POST** `/api/v1/media/upload/video`

Upload a video file for processing.

**Request:** `multipart/form-data`
```
video: <file> (MP4, AVI, MOV, MKV, WEBM - max 500MB)
original_filename: "my_video.mp4"
```

**Response:** `201 Created`
```json
{
  "media_input_id": 1,
  "input_type": "video",
  "video_id": 1,
  "video_format": "MP4",
  "original_filename": "my_video.mp4",
  "file_size_mb": 125,
  "duration_seconds": 180,
  "resolution": "1080",
  "frame_rate": 30,
  "file_path": "uploads/videos/user_1/video_1.mp4",
  "created_at": "2025-12-24T10:00:00Z"
}
```

**Error Responses:**
- `400 Bad Request` - Invalid file format
- `413 Payload Too Large` - File exceeds 500MB

---

### Upload Audio
**POST** `/api/v1/media/upload/audio`

Upload an audio file for processing.

**Request:** `multipart/form-data`
```
audio: <file> (MP3, WAV, AAC, FLAC, OGG - max 100MB)
original_filename: "my_audio.mp3"
```

**Response:** `201 Created`
```json
{
  "media_input_id": 2,
  "input_type": "audio",
  "audio_id": 1,
  "audio_format": "MP3",
  "original_filename": "my_audio.mp3",
  "file_size_mb": 8,
  "duration_seconds": 240,
  "file_path": "uploads/audio/user_1/audio_1.mp3",
  "created_at": "2025-12-24T10:05:00Z"
}
```

---

### Upload Text
**POST** `/api/v1/media/upload/text`

Upload text content or text file for processing.

**Request Body:**
```json
{
  "text_content": "This is the text content to be translated and dubbed...",
  "original_filename": "script.txt"
}
```

**Or multipart/form-data:**
```
text_file: <file> (TXT, SRT - max 10MB)
```

**Response:** `201 Created`
```json
{
  "media_input_id": 3,
  "input_type": "text",
  "text_id": 1,
  "original_filename": "script.txt",
  "word_count": 450,
  "file_size_mb": 0.05,
  "file_path": "uploads/text/user_1/text_1.txt",
  "created_at": "2025-12-24T10:10:00Z"
}
```

---

### Get Media Input Details
**GET** `/api/v1/media/{media_input_id}`

Get details of a specific media input.

**Response:** `200 OK`
```json
{
  "media_input_id": 1,
  "input_type": "video",
  "video_details": {
    "video_id": 1,
    "video_format": "MP4",
    "original_filename": "my_video.mp4",
    "file_size_mb": 125,
    "duration_seconds": 180,
    "resolution": "1080",
    "frame_rate": 30,
    "video_url": "https://storage.dabljaar.com/videos/video_1_preview.mp4"
  },
  "created_at": "2025-12-24T10:00:00Z"
}
```

---

### Delete Media Input
**DELETE** `/api/v1/media/{media_input_id}`

Delete a media input and its associated file.

**Response:** `204 No Content`

**Error Responses:**
- `409 Conflict` - Cannot delete media input used in active tasks

---

## Task Management

### Create Task
**POST** `/api/v1/tasks`

Create a new dubbing/translation task.

**Request Body:**
```json
{
  "name": "Educational Video Dubbing",
  "description": "Dub educational content from English to Arabic",
  "media_input_id": 1,
  "source_language": "EN",
  "target_language": "AR",
  "voice_id": 5,
  "domain_id": 2,
  "enable_dubbing": true,
  "enable_audio": true,
  "enable_subtitles": true
}
```

**Response:** `201 Created`
```json
{
  "task_id": 1,
  "user_id": 1,
  "name": "Educational Video Dubbing",
  "description": "Dub educational content from English to Arabic",
  "media_input_id": 1,
  "status": "pending",
  "source_language": "EN",
  "target_language": "AR",
  "voice_id": 5,
  "domain_id": 2,
  "enable_dubbing": true,
  "enable_audio": true,
  "enable_subtitles": true,
  "created_at": "2025-12-24T10:00:00Z",
  "estimated_completion": "2025-12-24T10:30:00Z"
}
```

---

### List All Tasks
**GET** `/api/v1/tasks`

Get all tasks for the authenticated user.

**Query Parameters:**
- `status` (string, optional): Filter by status (pending, in_progress, success, failure, cancelled)
- `source_language` (string, optional): Filter by source language
- `target_language` (string, optional): Filter by target language
- `sort_by` (string, default: created_at): Sort field
- `order` (string, default: desc): Sort order (asc, desc)
- `limit` (integer, default: 20)
- `offset` (integer, default: 0)

**Response:** `200 OK`
```json
{
  "tasks": [
    {
      "task_id": 1,
      "name": "Educational Video Dubbing",
      "status": "success",
      "source_language": "EN",
      "target_language": "AR",
      "created_at": "2025-12-24T10:00:00Z",
      "completed_at": "2025-12-24T10:25:00Z",
      "processing_time_seconds": 1500,
      "has_outputs": true
    },
    {
      "task_id": 2,
      "name": "Podcast Episode Translation",
      "status": "in_progress",
      "source_language": "EN",
      "target_language": "AR",
      "created_at": "2025-12-24T11:00:00Z",
      "progress_percentage": 65
    }
  ],
  "total": 15,
  "limit": 20,
  "offset": 0
}
```

---

### Get Task Details
**GET** `/api/v1/tasks/{task_id}`

Get detailed information about a specific task.

**Response:** `200 OK`
```json
{
  "task_id": 1,
  "user_id": 1,
  "name": "Educational Video Dubbing",
  "description": "Dub educational content from English to Arabic",
  "media_input": {
    "media_input_id": 1,
    "input_type": "video",
    "duration_seconds": 180
  },
  "status": "success",
  "source_language": "EN",
  "target_language": "AR",
  "voice": {
    "voice_id": 5,
    "name": "محمد - احترافي"
  },
  "domain": {
    "domain_id": 2,
    "name": "Medical"
  },
  "enable_dubbing": true,
  "enable_audio": true,
  "enable_subtitles": true,
  "created_at": "2025-12-24T10:00:00Z",
  "updated_at": "2025-12-24T10:25:00Z",
  "completed_at": "2025-12-24T10:25:00Z",
  "processing_time_seconds": 1500,
  "outputs": [
    {
      "output_id": 1,
      "output_type": "video",
      "file_size_mb": 130
    }
  ]
}
```

---

### Update Task
**PUT** `/api/v1/tasks/{task_id}`

Update task details (only for pending tasks).

**Request Body:**
```json
{
  "name": "Updated Task Name",
  "description": "Updated description",
  "voice_id": 6
}
```

**Response:** `200 OK`
```json
{
  "task_id": 1,
  "name": "Updated Task Name",
  "description": "Updated description",
  "voice_id": 6,
  "updated_at": "2025-12-24T10:30:00Z"
}
```

**Error Responses:**
- `400 Bad Request` - Cannot update task that is not pending

---

### Cancel Task
**PATCH** `/api/v1/tasks/{task_id}/cancel`

Cancel a pending or in-progress task.

**Response:** `200 OK`
```json
{
  "task_id": 1,
  "status": "cancelled",
  "message": "Task cancelled successfully"
}
```

**Error Responses:**
- `400 Bad Request` - Cannot cancel completed task

---

### Delete Task
**DELETE** `/api/v1/tasks/{task_id}`

Delete a task and its outputs.

**Response:** `204 No Content`

---

### Get Task Status
**GET** `/api/v1/tasks/{task_id}/status`

Get real-time status of a task (lightweight endpoint for polling).

**Response:** `200 OK`
```json
{
  "task_id": 1,
  "status": "in_progress",
  "progress_percentage": 65,
  "current_step": "Generating dubbed audio",
  "estimated_completion": "2025-12-24T10:25:00Z",
  "updated_at": "2025-12-24T10:18:00Z"
}
```

---

## Output Management

### List All Outputs
**GET** `/api/v1/outputs`

Get all outputs for the authenticated user.

**Query Parameters:**
- `task_id` (integer, optional): Filter by task
- `output_type` (string, optional): Filter by type (audio, video)
- `limit` (integer, default: 20)
- `offset` (integer, default: 0)

**Response:** `200 OK`
```json
{
  "outputs": [
    {
      "output_id": 1,
      "task_id": 1,
      "task_name": "Educational Video Dubbing",
      "output_type": "video",
      "file_size_mb": 130,
      "generated_at": "2025-12-24T10:25:00Z",
      "download_url": "https://storage.dabljaar.com/outputs/output_1.mp4"
    },
    {
      "output_id": 2,
      "task_id": 1,
      "task_name": "Educational Video Dubbing",
      "output_type": "audio",
      "file_size_mb": 12,
      "generated_at": "2025-12-24T10:25:00Z",
      "download_url": "https://storage.dabljaar.com/outputs/output_2.mp3"
    }
  ],
  "total": 8,
  "limit": 20,
  "offset": 0
}
```

---

### Get Output Details
**GET** `/api/v1/outputs/{output_id}`

Get detailed information about a specific output.

**Response:** `200 OK`
```json
{
  "output_id": 1,
  "user_id": 1,
  "task": {
    "task_id": 1,
    "name": "Educational Video Dubbing"
  },
  "output_type": "video",
  "file_path": "outputs/user_1/video_1_dubbed.mp4",
  "file_size_mb": 130,
  "generated_at": "2025-12-24T10:25:00Z",
  "download_url": "https://storage.dabljaar.com/outputs/output_1.mp4",
  "video_details": {
    "video_id": 1,
    "language": "AR",
    "duration_seconds": 180,
    "audio_track": {
      "audio_id": 1,
      "voice_name": "محمد - احترافي"
    }
  },
  "has_subtitles": true,
  "subtitle_count": 1
}
```

---

### Download Output
**GET** `/api/v1/outputs/{output_id}/download`

Download output file (returns file or redirect to signed URL).

**Response:** `200 OK` or `302 Redirect`

File download or redirect to temporary signed URL.

---

### Get Output Subtitles
**GET** `/api/v1/outputs/{output_id}/subtitles`

Get subtitles associated with an output.

**Response:** `200 OK`
```json
{
  "subtitles": [
    {
      "subtitle_id": 1,
      "language": "AR",
      "word_count": 420,
      "char_count": 2150,
      "file_size_mb": 0.05,
      "download_url": "https://storage.dabljaar.com/subtitles/subtitle_1.srt"
    }
  ]
}
```

---

### Download Subtitle File
**GET** `/api/v1/outputs/{output_id}/subtitles/{subtitle_id}/download`

Download subtitle file in SRT format.

**Response:** `200 OK`

Returns SRT file.

---

### Get Output Audio
**GET** `/api/v1/outputs/{output_id}/audio`

Get audio track details for an output.

**Response:** `200 OK`
```json
{
  "audio_id": 1,
  "voice": {
    "voice_id": 5,
    "name": "محمد - احترافي"
  },
  "language": "AR",
  "duration_seconds": 180,
  "file_size_mb": 12,
  "download_url": "https://storage.dabljaar.com/audio/audio_1.mp3"
}
```

---

### Get Output Video
**GET** `/api/v1/outputs/{output_id}/video`

Get video details for an output.

**Response:** `200 OK`
```json
{
  "video_id": 1,
  "language": "AR",
  "duration_seconds": 180,
  "file_size_mb": 130,
  "resolution": "1080",
  "audio_track": {
    "audio_id": 1,
    "voice_name": "محمد - احترافي"
  },
  "download_url": "https://storage.dabljaar.com/videos/video_1_dubbed.mp4"
}
```

---

### Delete Output
**DELETE** `/api/v1/outputs/{output_id}`

Delete an output and its associated files.

**Response:** `204 No Content`

---

## Admin Endpoints (Future Implementation)

### User Management
- `GET /api/v1/admin/users` - List all users
- `GET /api/v1/admin/users/{user_id}` - Get user details
- `PATCH /api/v1/admin/users/{user_id}/suspend` - Suspend user
- `PATCH /api/v1/admin/users/{user_id}/activate` - Activate user

### Subscription Plan Management
- `POST /api/v1/admin/plans` - Create subscription plan
- `PUT /api/v1/admin/plans/{plan_id}` - Update plan
- `DELETE /api/v1/admin/plans/{plan_id}` - Delete plan

### System Analytics
- `GET /api/v1/admin/analytics/usage` - System usage statistics
- `GET /api/v1/admin/analytics/revenue` - Revenue analytics
- `GET /api/v1/admin/analytics/tasks` - Task completion statistics

---

## Error Codes

### Standard HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | OK - Request successful |
| `201` | Created - Resource created successfully |
| `202` | Accepted - Request accepted for processing |
| `204` | No Content - Request successful, no content to return |
| `400` | Bad Request - Invalid request parameters |
| `401` | Unauthorized - Authentication required or failed |
| `403` | Forbidden - Insufficient permissions |
| `404` | Not Found - Resource not found |
| `409` | Conflict - Resource conflict (e.g., duplicate) |
| `413` | Payload Too Large - File size exceeds limit |
| `422` | Unprocessable Entity - Validation error |
| `429` | Too Many Requests - Rate limit exceeded |
| `500` | Internal Server Error - Server error |
| `503` | Service Unavailable - Service temporarily unavailable |

---

### Error Response Format

All error responses follow this format:

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "Validation error in request body",
    "details": [
      {
        "field": "email",
        "message": "Invalid email format"
      }
    ],
    "timestamp": "2025-12-24T10:00:00Z",
    "request_id": "req_abc123"
  }
}
```

---

### Common Error Codes

| Error Code | Description |
|------------|-------------|
| `INVALID_INPUT` | Request validation failed |
| `UNAUTHORIZED` | Authentication failed |
| `FORBIDDEN` | Insufficient permissions |
| `NOT_FOUND` | Resource not found |
| `DUPLICATE_RESOURCE` | Resource already exists |
| `RATE_LIMIT_EXCEEDED` | Too many requests |
| `SUBSCRIPTION_REQUIRED` | Premium subscription required |
| `INSUFFICIENT_CREDITS` | Not enough credits/usage quota |
| `FILE_TOO_LARGE` | Uploaded file exceeds size limit |
| `INVALID_FILE_FORMAT` | Unsupported file format |
| `PROCESSING_ERROR` | Error during task processing |
| `PAYMENT_FAILED` | Payment processing failed |

---

## Rate Limiting

API requests are rate-limited based on subscription plan:

| Plan | Rate Limit |
|------|------------|
| Free | 60 requests/hour |
| Pro | 300 requests/hour |
| Enterprise | 1000 requests/hour |

Rate limit headers are included in all responses:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1640000000
```

---

## Pagination

List endpoints support pagination with the following query parameters:

- `limit` (integer): Number of items per page (default: 20, max: 100)
- `offset` (integer): Number of items to skip (default: 0)

Pagination response format:

```json
{
  "data": [...],
  "total": 150,
  "limit": 20,
  "offset": 0,
  "has_more": true
}
```

---

## Webhooks (Future)

Users can register webhooks for the following events:

- `task.created` - New task created
- `task.processing` - Task processing started
- `task.completed` - Task completed successfully
- `task.failed` - Task processing failed
- `subscription.renewed` - Subscription renewed
- `subscription.cancelled` - Subscription cancelled
- `payment.completed` - Payment successful

---

## SDK & Client Libraries (Future)

Official client libraries will be available for:

- Python
- JavaScript/TypeScript
- Java
- PHP

---

## Support

For API support, contact:
- Email: api-support@dabljaar.com
- Documentation: https://docs.dabljaar.com
- Status Page: https://status.dabljaar.com