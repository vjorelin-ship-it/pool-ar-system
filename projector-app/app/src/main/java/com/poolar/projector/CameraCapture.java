package com.poolar.projector;

import android.content.Context;
import android.graphics.ImageFormat;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.media.Image;
import android.media.ImageReader;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Log;
import android.view.Surface;

import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.ArrayList;

public class CameraCapture {
    private static final String TAG = "CameraCapture";
    private CameraManager cameraManager;
    private CameraDevice cameraDevice;
    private CameraCaptureSession captureSession;
    private ImageReader imageReader;
    private Handler backgroundHandler;
    private HandlerThread backgroundThread;
    private FrameCallback frameCallback;
    private int targetWidth = 2560;
    private int targetHeight = 1440;

    public interface FrameCallback {
        void onFrame(byte[] jpegData, long timestamp);
    }

    public CameraCapture(Context context, FrameCallback callback) {
        this.cameraManager = (CameraManager) context.getSystemService(Context.CAMERA_SERVICE);
        this.frameCallback = callback;
    }

    public void setResolution(int width, int height) {
        this.targetWidth = width;
        this.targetHeight = height;
    }

    public void start() {
        startBackgroundThread();
        try {
            String cameraId = findUsbCamera();
            if (cameraId == null) {
                Log.w(TAG, "No USB camera found, using first available");
                String[] ids = cameraManager.getCameraIdList();
                if (ids.length == 0) {
                    Log.e(TAG, "No camera available");
                    return;
                }
                cameraId = ids[0];
            }
            Log.d(TAG, "Opening camera: " + cameraId);
            cameraManager.openCamera(cameraId, stateCallback, backgroundHandler);
        } catch (SecurityException e) {
            Log.e(TAG, "Camera permission denied", e);
        } catch (CameraAccessException e) {
            Log.e(TAG, "Camera access error", e);
        }
    }

    public void stop() {
        try {
            if (captureSession != null) {
                captureSession.close();
                captureSession = null;
            }
        } catch (Exception e) { Log.e(TAG, "Error closing session", e); }
        try {
            if (cameraDevice != null) {
                cameraDevice.close();
                cameraDevice = null;
            }
        } catch (Exception e) { Log.e(TAG, "Error closing camera", e); }
        if (imageReader != null) {
            imageReader.close();
            imageReader = null;
        }
        stopBackgroundThread();
    }

    private String findUsbCamera() throws CameraAccessException {
        for (String id : cameraManager.getCameraIdList()) {
            CameraCharacteristics chars = cameraManager.getCameraCharacteristics(id);
            Integer facing = chars.get(CameraCharacteristics.LENS_FACING);
            if (facing != null && facing == CameraCharacteristics.LENS_FACING_EXTERNAL) {
                return id;
            }
        }
        return null;
    }

    private final CameraDevice.StateCallback stateCallback = new CameraDevice.StateCallback() {
        @Override
        public void onOpened(CameraDevice device) {
            cameraDevice = device;
            createCaptureSession();
        }
        @Override
        public void onDisconnected(CameraDevice device) {
            device.close();
            cameraDevice = null;
            Log.w(TAG, "Camera disconnected, retrying in 3s");
            new Handler(backgroundThread.getLooper()).postDelayed(() -> start(), 3000);
        }
        @Override
        public void onError(CameraDevice device, int error) {
            device.close();
            cameraDevice = null;
            Log.e(TAG, "Camera error: " + error);
        }
    };

    private void createCaptureSession() {
        try {
            imageReader = ImageReader.newInstance(
                targetWidth, targetHeight, ImageFormat.JPEG, 2);
            imageReader.setOnImageAvailableListener(readerListener, backgroundHandler);

            List<Surface> surfaces = new ArrayList<>();
            surfaces.add(imageReader.getSurface());
            cameraDevice.createCaptureSession(surfaces, sessionCallback, backgroundHandler);
        } catch (CameraAccessException e) {
            Log.e(TAG, "Failed to create capture session", e);
        }
    }

    private final CameraCaptureSession.StateCallback sessionCallback =
        new CameraCaptureSession.StateCallback() {
            @Override
            public void onConfigured(CameraCaptureSession session) {
                captureSession = session;
                startRepeatingCapture();
            }
            @Override
            public void onConfigureFailed(CameraCaptureSession session) {
                Log.e(TAG, "Session configuration failed");
            }
        };

    private void startRepeatingCapture() {
        try {
            CaptureRequest.Builder builder = cameraDevice.createCaptureRequest(
                CameraDevice.TEMPLATE_PREVIEW);
            builder.addTarget(imageReader.getSurface());
            builder.set(CaptureRequest.JPEG_QUALITY, (byte) 70);
            captureSession.setRepeatingRequest(builder.build(), null, backgroundHandler);
        } catch (CameraAccessException e) {
            Log.e(TAG, "Failed to start repeating capture", e);
        }
    }

    private final ImageReader.OnImageAvailableListener readerListener =
        new ImageReader.OnImageAvailableListener() {
            @Override
            public void onImageAvailable(ImageReader reader) {
                Image image = reader.acquireLatestImage();
                if (image == null) return;
                try {
                    ByteBuffer buffer = image.getPlanes()[0].getBuffer();
                    byte[] jpegData = new byte[buffer.remaining()];
                    buffer.get(jpegData);
                    if (frameCallback != null) {
                        frameCallback.onFrame(jpegData, image.getTimestamp());
                    }
                } finally {
                    image.close();
                }
            }
        };

    private void startBackgroundThread() {
        if (backgroundThread != null) return;
        backgroundThread = new HandlerThread("CameraBackground");
        backgroundThread.start();
        backgroundHandler = new Handler(backgroundThread.getLooper());
    }

    private void stopBackgroundThread() {
        if (backgroundThread != null) {
            backgroundThread.quitSafely();
            try { backgroundThread.join(); } catch (InterruptedException e) {}
            backgroundThread = null;
            backgroundHandler = null;
        }
    }
}
