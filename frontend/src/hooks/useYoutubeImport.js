import { useState } from 'react';
import toast from 'react-hot-toast';
import { mediaService } from '../services/mediaService';
import { useTranslation } from './useTranslation';

export const useYoutubeImport = (onSuccessCallback, hideModalCallback) => {
  const { t } = useTranslation();
  const [showYoutubeModal, setShowYoutubeModal] = useState(false);
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [youtubeFormat, setYoutubeFormat] = useState('video');
  const [youtubeQuality, setYoutubeQuality] = useState('720p');
  const [isYoutubeDownloading, setIsYoutubeDownloading] = useState(false);
  const [youtubeError, setYoutubeError] = useState(null);
  const [selectedYoutubeInfo, setSelectedYoutubeInfo] = useState(null);

  const resetYoutubeState = () => {
    setYoutubeUrl('');
    setSelectedYoutubeInfo(null);
    setYoutubeError(null);
    if (hideModalCallback) hideModalCallback();
    setShowYoutubeModal(false);
  };

  const handleYoutubeImportOnly = async (urlOverride = null) => {
    const targetUrl = urlOverride || (selectedYoutubeInfo ? selectedYoutubeInfo.url : youtubeUrl);
    const targetFormat = selectedYoutubeInfo?.format || youtubeFormat;
    const targetQuality = selectedYoutubeInfo?.quality || youtubeQuality;

    if (!targetUrl.trim()) {
      setYoutubeError(t('originalVideos.youtubeErrorEmpty') || 'Please enter a URL');
      return;
    }
    const ytRegex = /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?.*v=[\w-]+|shorts\/[\w-]+)|youtu\.be\/[\w-]+)/;
    if (!ytRegex.test(targetUrl.trim())) {
      setYoutubeError(t('originalVideos.youtubeErrorInvalid') || 'Invalid YouTube URL');
      return;
    }

    setIsYoutubeDownloading(true);
    setYoutubeError(null);

    try {
      await mediaService.downloadFromYoutube({
        youtube_url: targetUrl.trim(),
        format: targetFormat,
        quality: targetQuality,
        output_type: 'uploadOnly'
      });

      toast.success(t('originalVideos.youtubeSuccessMsg') || 'YouTube download queued!');
      resetYoutubeState();
      if (onSuccessCallback) onSuccessCallback();
    } catch (err) {
      console.error('YouTube download failed:', err);
      if (showYoutubeModal) setYoutubeError(err.message || 'Failed to queue YouTube download.');
      else toast.error(err.message || 'Failed to queue YouTube download.');
    } finally {
      setIsYoutubeDownloading(false);
    }
  };

  const handleYoutubeSelection = () => {
    if (!youtubeUrl.trim()) {
      setYoutubeError(t('originalVideos.youtubeErrorEmpty') || 'Please enter a URL');
      return;
    }
    const ytRegex = /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?.*v=[\w-]+|shorts\/[\w-]+)|youtu\.be\/[\w-]+)/;
    if (!ytRegex.test(youtubeUrl.trim())) {
      setYoutubeError(t('originalVideos.youtubeErrorInvalid') || 'Invalid YouTube URL');
      return;
    }

    setSelectedYoutubeInfo({
      url: youtubeUrl,
      format: youtubeFormat,
      quality: youtubeQuality
    });
    setShowYoutubeModal(false);
    setYoutubeUrl('');
  };

  return {
    showYoutubeModal,
    setShowYoutubeModal,
    youtubeUrl,
    setYoutubeUrl,
    youtubeFormat,
    setYoutubeFormat,
    youtubeQuality,
    setYoutubeQuality,
    isYoutubeDownloading,
    youtubeError,
    setYoutubeError,
    selectedYoutubeInfo,
    setSelectedYoutubeInfo,
    handleYoutubeImportOnly,
    handleYoutubeSelection,
    resetYoutubeState
  };
};
