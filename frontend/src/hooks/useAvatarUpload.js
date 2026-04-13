import { useState, useRef } from 'react';
import toast from 'react-hot-toast';

export const useAvatarUpload = (onUploadSuccess, onError) => {
  const [avatarFile, setAvatarFile] = useState(null);
  const [avatarPreview, setAvatarPreview] = useState(null);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const fileInputRef = useRef(null);

  const handleAvatarChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      // Validate file type
      const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
      if (!validTypes.includes(file.type)) {
        if (onError) onError('invalid_type');
        else toast.error('Please select a valid image file (jpg, png, gif, webp)');
        return;
      }

      // Validate file size (5MB)
      if (file.size > 5 * 1024 * 1024) {
        if (onError) onError('invalid_size');
        else toast.error('File size must be less than 5MB');
        return;
      }

      setAvatarFile(file);

      // Create preview
      const reader = new FileReader();
      reader.onloadend = () => {
        setAvatarPreview(reader.result);
      };
      reader.readAsDataURL(file);
    }
  };

  const uploadAvatar = async (fileToUpload = avatarFile) => {
    if (!fileToUpload) return null;
    
    const formData = new FormData();
    formData.append('file', fileToUpload);

    setUploadingAvatar(true);
    try {
      const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
      if (!API_BASE_URL) {
        throw new Error('VITE_API_BASE_URL environment variable is required');
      }

      const response = await fetch(`${API_BASE_URL}/upload/avatar`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to upload avatar');
      }

      const data = await response.json();
      if (onUploadSuccess) onUploadSuccess(data.url);
      return data.url;
    } catch (error) {
      if (onError) onError(error.message);
      throw error;
    } finally {
      setUploadingAvatar(false);
    }
  };

  const resetAvatar = () => {
    setAvatarFile(null);
    setAvatarPreview(null);
  };
  
  const triggerFileInput = () => {
    if (fileInputRef.current) {
        fileInputRef.current.click();
    }
  }

  return {
    avatarFile,
    avatarPreview,
    uploadingAvatar,
    fileInputRef,
    handleAvatarChange,
    uploadAvatar,
    resetAvatar,
    triggerFileInput,
    setAvatarPreview
  };
};
