import React, { useState, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { mediaService } from '../../services/mediaService';
import '../../styles/home.css';

const TryItNowSection = () => {
    const { isAuthenticated } = useAuth();
    const navigate = useNavigate();
    const fileInputRef = useRef(null);
    const [isDragOver, setIsDragOver] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState(null);

    const handleDragOver = (e) => {
        e.preventDefault();
        setIsDragOver(true);
    };

    const handleDragLeave = (e) => {
        e.preventDefault();
        setIsDragOver(false);
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setIsDragOver(false);
        if (!isAuthenticated) return;
        const file = e.dataTransfer.files?.[0];
        if (file) handleFile(file);
    };

    const handleFileSelect = (e) => {
        const file = e.target.files?.[0];
        if (file) handleFile(file);
    };

    const handleFile = async (file) => {
        // Validate
        const validExtensions = ['.mp4', '.avi', '.mov', '.mkv'];
        const fileExt = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
        if (!file.type.startsWith('video/') && !validExtensions.includes(fileExt)) {
            setError('Invalid file format. Please upload MP4, AVI, or MOV.');
            return;
        }

        if (file.size > 500 * 1024 * 1024) { // 500MB
            setError('File size exceeds 500MB limit.');
            return;
        }

        setError(null);
        setIsUploading(true);

        try {
            const formData = new FormData();
            formData.append('file', file);

            // Upload
            await mediaService.uploadVideo(formData);

            // Redirect to dashboard
            navigate('/dashboard');
        } catch (err) {
            console.error(err);
            setError('Upload failed. Please try again.');
            setIsUploading(false);
        }
    };

    const triggerFileInput = () => {
        if (!isAuthenticated) return;
        fileInputRef.current?.click();
    };

    return (
        <section id="demo" className="try-it-now-section">
            <div className="container">
                <div className="try-it-header">
                    <span className="section-eyebrow">Try It Now</span>
                    <h2 className="section-title-custom">
                        {isAuthenticated ? 'Upload Your Video' : 'Join to Start Dubbing'}
                    </h2>
                    <p className="section-description">Experience the power of AI dubbing in seconds</p>
                </div>

                <div
                    className={`upload-dropzone ${isDragOver ? 'drag-over' : ''} ${isUploading ? 'uploading' : ''}`}
                    onDragOver={isAuthenticated ? handleDragOver : undefined}
                    onDragLeave={isAuthenticated ? handleDragLeave : undefined}
                    onDrop={isAuthenticated ? handleDrop : undefined}
                    onClick={isAuthenticated && !isUploading ? triggerFileInput : undefined}
                    style={{ cursor: isAuthenticated ? 'pointer' : 'default', opacity: isAuthenticated ? 1 : 1 }}
                >
                    {isAuthenticated ? (
                        <>
                            <input
                                type="file"
                                ref={fileInputRef}
                                aria-label="Upload Video"
                                hidden
                                accept="video/*,.mp4,.mov,.avi,.mkv"
                                onChange={handleFileSelect}
                                disabled={isUploading}
                            />

                            {isUploading ? (
                                <div className="upload-status">
                                    <div className="spinner"></div>
                                    <h3>Uploading and Processing...</h3>
                                    <p>Please wait while we prepare your dashboard.</p>
                                </div>
                            ) : (
                                <div className="upload-content">
                                    <div className="upload-icon-large">📤</div>
                                    <h3>Drag & Drop Your Video</h3>
                                    <p className="upload-sub">or click to browse files</p>

                                    <button className="btn btn-primary choose-file-btn">
                                        Choose File
                                    </button>

                                    <div className="upload-features">
                                        <div className="upload-feature-item">
                                            <span className="check-icon">✓</span>
                                            <span>Max size: 500MB</span>
                                        </div>
                                        <div className="upload-feature-item">
                                            <span className="check-icon">✓</span>
                                            <span>Formats: MP4, AVI, MOV</span>
                                        </div>
                                        <div className="upload-feature-item">
                                            <span className="check-icon">✓</span>
                                            <span>Processing: ~2 minutes</span>
                                        </div>
                                    </div>
                                </div>
                            )}
                            {error && <div className="upload-error">{error}</div>}
                        </>
                    ) : (
                        // Guest State
                        <div className="upload-content guest-content">
                            <div className="upload-icon-large" style={{ opacity: 0.5 }}>🔒</div>
                            <h3>Sign Up to Upload Videos</h3>
                            <p className="upload-sub">Create a free account to start dubbing your videos today.</p>

                            <div style={{ display: 'flex', gap: '16px', justifyContent: 'center', marginBottom: '32px' }}>
                                <Link to="/register" className="btn btn-primary">
                                    Create Free Account
                                </Link>
                                <Link to="/login" className="btn btn-secondary-outline">
                                    Login
                                </Link>
                            </div>

                            <div className="upload-features">
                                <div className="upload-feature-item">
                                    <span className="check-icon">✓</span>
                                    <span>5 Free Credits</span>
                                </div>
                                <div className="upload-feature-item">
                                    <span className="check-icon">✓</span>
                                    <span>Fast Processing</span>
                                </div>
                                <div className="upload-feature-item">
                                    <span className="check-icon">✓</span>
                                    <span>High Quality AI Voices</span>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </section>
    );
};

export default TryItNowSection;
