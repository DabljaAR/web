# Media Service Implementation Report

## 1. Summary of Work Done
We have successfully implemented a robust **Video Processing Pipeline** designed to handle the complete lifecycle of media files within the DabljaAR platform.

**Key Features Implemented:**
*   **Video Upload API**: Secure and efficient endpoints to upload video files directly to our storage system.
*   **Smart Storage Mechanism**: A flexible storage layer that seamlessly integrates with **MinIO** (S3-compatible) while maintaining the ability to fall back to local storage for development flexibility.
*   **Automated Background Processing**:
    *   **Zero-Wait Uploads**: The system processes videos in the background immediately after upload, ensuring the user interface remains responsive.
    *   **FFmpeg Integration**: Automatic scanning of video files to extract richer metadata (duration, resolution, codec, frame rate).
    *   **Asset Generation**: Capabilities to automatically extract the **audio track** (MP3) and generate a **thumbnail image** for every uploaded video.
*   **Automated Cleanup**: implemented an "Observer-like" behavior where deleting a video record from the database triggers the automatic removal of the associated video, audio, and thumbnail files from storage, keeping the system clean and efficient.

## 2. Why MinIO? (The AWS Connection)
We deliberately chose **MinIO** because of its native **S3 Compatibility**.

*   **The "Secret" Weapon (Boto3)**: Our backend utilizes the `aioboto3` library (an asynchronous wrapper around Amazon's official `boto3` SDK). This is the industry-standard library for interacting with **AWS S3**.
*   **Future-Proof Architecture**: By using this library, our code "speaks" the native language of AWS cloud storage.
*   **Seamless Migration**: If you ever decide to move from self-hosted MinIO to AWS S3, **0 lines of code need to change**. You simply update your configuration file with your AWS credentials (API Key & Region), and the system will instantly work with the improved infrastructure.

## 3. Block Storage vs. Object Storage (Simplified)

To understand why we chose this architecture, here is a simple comparison:

### Block Storage (Like a Parking Garage)
*   **Concept**: Think of a traditional hard drive or a parking garage with specific, numbered spots.
*   **How it works**: Data is split into small, fixed-size chunks ("blocks"). You can modify tiny specific parts of a file without rewriting the whole thing.
*   **Best For**: Databases, Operation Systems, and high-performance applications where data changes frequently.
*   **Downside**: It can be expensive and difficult to scale when managing terabytes of unstructured data.

### Object Storage (Like Valet Parking)
*   **Concept**: Think of Valet Parking. You hand over your car (the file), and you receive a ticket (a unique ID/URL). You don't need to know *where* it is parked, just that you can get it back with your ticket.
*   **How it works**: It stores the **entire file** as one "Object" along with its metadata (info about the file).
*   **Best For**: Storing massive amounts of unstructured data like **Videos, Images, Backups, and Logs**.
*   **Upside**: Infinitely scalable, cost-effective for large files, and accessible via simple HTTP APIs.

### Why We Use Object Storage (MinIO)
We chose Object Storage because we are building a **Media-First Application**:
1.  **Large Files**: Videos are essentially large "blobs" of data. We write them once and read them many times ("Write Once, Read Many"). We almost never need to edit a single byte in the middle of a video file directly on the disk.
2.  **Scalability**: As users upload more content, our storage needs will explode. Object storage allows you to add capacity easily without disrupting the application.
3.  **Separation of Concerns**: It decouples storage from the application logic. The API server handles the business rules, while MinIO handles the heavy lifting of storing and serving the media files reliably.
