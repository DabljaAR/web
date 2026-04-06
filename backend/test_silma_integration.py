#!/usr/bin/env python3
"""
Quick test script for SILMA-TTS integration.

This script verifies that SILMA-TTS can be imported and instantiated correctly.
Run this after installing silma-tts to verify the installation.
"""

import sys
import os

def test_silma_import():
    """Test if SILMA-TTS can be imported."""
    print("Testing SILMA-TTS import...")
    try:
        from silma_tts.api import SilmaTTS
        print("✓ SILMA-TTS import successful")
        return True
    except ImportError as e:
        print(f"✗ Failed to import SILMA-TTS: {e}")
        print("  Install with: pip install silma-tts")
        return False

def test_silma_instantiation():
    """Test if SILMA-TTS model can be instantiated."""
    print("\nTesting SILMA-TTS model instantiation...")
    try:
        from silma_tts.api import SilmaTTS
        model = SilmaTTS()
        print("✓ SILMA-TTS model loaded successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to load SILMA-TTS model: {e}")
        return False

def test_config():
    """Test if configuration is set up correctly."""
    print("\nTesting configuration...")
    try:
        from app.config import settings
        
        checks = [
            ("SILMA_DEVICE", settings.SILMA_DEVICE),
            ("SILMA_REFERENCE_AUDIO", settings.SILMA_REFERENCE_AUDIO),
            ("TTS_DEFAULT_SPEED", settings.TTS_DEFAULT_SPEED),
            ("TTS_DEFAULT_CFG_STRENGTH", settings.TTS_DEFAULT_CFG_STRENGTH),
            ("TTS_DEFAULT_NFE_STEP", settings.TTS_DEFAULT_NFE_STEP),
        ]
        
        for name, value in checks:
            print(f"  {name}: {value}")
        
        # Check if reference audio exists
        if settings.SILMA_REFERENCE_AUDIO:
            if os.path.exists(settings.SILMA_REFERENCE_AUDIO):
                print(f"✓ Reference audio found at: {settings.SILMA_REFERENCE_AUDIO}")
            else:
                print(f"⚠ Warning: Reference audio not found at: {settings.SILMA_REFERENCE_AUDIO}")
                print("  Set SILMA_REFERENCE_AUDIO in .env to a valid audio file path")
        else:
            print("⚠ Warning: SILMA_REFERENCE_AUDIO not set in .env")
            print("  This is required for TTS synthesis to work")
        
        print("✓ Configuration loaded successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to load configuration: {e}")
        return False

def test_model_manager():
    """Test if the model manager can be imported."""
    print("\nTesting model manager...")
    try:
        from app.tts.models import SilmaTTSModelManager
        print("✓ SilmaTTSModelManager imported successfully")
        
        # Try to instantiate (lazy load)
        manager = SilmaTTSModelManager()
        device = manager.device
        print(f"  Device: {device}")
        
        return True
    except Exception as e:
        print(f"✗ Failed to load model manager: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("SILMA-TTS Integration Test")
    print("=" * 60)
    
    results = []
    
    # Test 1: Import
    results.append(("Import", test_silma_import()))
    
    # Test 2: Config
    results.append(("Configuration", test_config()))
    
    # Test 3: Model Manager
    results.append(("Model Manager", test_model_manager()))
    
    # Test 4: Model Instantiation (only if import succeeded)
    if results[0][1]:
        results.append(("Model Instantiation", test_silma_instantiation()))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:.<40} {status}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed! SILMA-TTS is ready to use.")
        return 0
    else:
        print("\n✗ Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
