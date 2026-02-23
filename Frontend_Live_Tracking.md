# Frontend Implementation Guide: Live Video Tracking

This document outlines the features and implementation steps required on the Next.js frontend to support the Live Video Tracking (AI Psychological Expert) architecture.

## 🎯 Core Features to Implement

1. **Webcam Integration**
   - securely request and access the user's camera stream using `navigator.mediaDevices.getUserMedia`.
   - Display the live feed in a mirrored `<video>` element for the candidate.
   
2. **Hidden Frame Capture**
   - Use an off-screen `<canvas>` element to capture still frames from the active video feed.
   - Downscale the captured frames to a low resolution (e.g., `320x240`) to save bandwidth.
   - Compress the frames into `base64` JPEG format (quality ~0.6).

3. **Real-time WebSocket Connection**
   - Establish a secure WebSocket connection to the FastAPI backend at `ws://<backend-url>/interview/ws/video-stream/{session_id}` upon starting the interview.
   - Handle connection lifecycle (open, close, reconnect on error).

4. **Intelligent Frame Throttling**
   - Implement an interval loop (e.g., `setInterval`) to capture and send frames strictly every 3 to 5 seconds.
   - **Crucial:** Only send frames when `isAnswering` is true (i.e., when the candidate is actively speaking, not when the AI interviewer is asking a question).

5. **Resource Cleanup**
   - Ensure all video tracks are stopped and WebSockets are closed when the component unmounts or the interview ends to prevent memory leaks and camera light remaining on.

---

## 💻 Component Implementation (`LiveVideoTracker.tsx`)

Here is the complete reference implementation for your Next.js frontend.

```tsx
// src/components/interview/LiveVideoTracker.tsx
import React, { useEffect, useRef, useState } from "react";

interface LiveVideoTrackerProps {
  sessionId: string;
  isAnswering: boolean; // True when candidate is speaking, false when AI is speaking
  isActive: boolean;    // Master switch to turn the camera/tracking on or off completely
}

export function LiveVideoTracker({ sessionId, isAnswering, isActive }: LiveVideoTrackerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);

  // 1. Initialize Camera Stream
  useEffect(() => {
    if (!isActive) return;

    let stream: MediaStream | null = null;
    
    async function startCamera() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ 
          video: { width: 1280, height: 720, facingMode: "user" },
          audio: false // We only need video for tracking
        });
        
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      } catch (err) {
        console.error("Failed to access camera:", err);
        setCameraError("Camera access denied or unavailable.");
      }
    }

    startCamera();

    // Cleanup: Stop camera tracks when unmounting or deactivated
    return () => {
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
      }
    };
  }, [isActive]);

  // 2. Establish WebSocket Connection
  useEffect(() => {
    if (!isActive || !sessionId) return;
    
    // Adjust URL based on your environment (ws:// for local, wss:// for production)
    const backendHost = process.env.NEXT_PUBLIC_BACKEND_URL?.replace("http", "ws") || "ws://127.0.0.1:8000";
    const wsUrl = `${backendHost}/interview/ws/video-stream/${sessionId}`;
    
    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => console.log("🟢 Connected to AI Behavioral Analysis");
    wsRef.current.onerror = (err) => console.error("🔴 Behavioral WS Error:", err);
    wsRef.current.onclose = () => console.log("⚪ Behavioral WS Closed");

    return () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
    };
  }, [isActive, sessionId]);

  // 3. Capture & Send Frame Loop
  useEffect(() => {
    let intervalId: NodeJS.Timeout;

    const captureAndSendFrame = () => {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      
      if (!video || !canvas || !wsRef.current) return;
      if (wsRef.current.readyState !== WebSocket.OPEN) return;

      const context = canvas.getContext("2d");
      if (context) {
        // Draw video frame to canvas at low resolution (Optimizes Vision API latency)
        canvas.width = 320; 
        canvas.height = 240;
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        // Convert to highly-compressed JPEG base64 (quality 0.5 - 0.6)
        const base64Data = canvas.toDataURL("image/jpeg", 0.6);
        
        // Send to FastAPI backend
        wsRef.current.send(JSON.stringify({
          action: "analyze_frame",
          image_b64: base64Data
        }));
      }
    };

    // Only send frames if tracking is active AND the candidate is actively answering
    if (isActive && isAnswering && videoRef.current) {
      intervalId = setInterval(captureAndSendFrame, 4000); // Send 1 frame every 4 seconds
    }

    return () => clearInterval(intervalId);
  }, [isActive, isAnswering]);

  if (!isActive) return null;

  return (
    <div className="relative w-full aspect-video bg-black rounded-lg overflow-hidden border border-gray-800 shadow-xl">
      {cameraError ? (
        <div className="absolute inset-0 flex items-center justify-center text-red-500 text-sm p-4 text-center">
          {cameraError}
        </div>
      ) : (
        <video 
          ref={videoRef} 
          autoPlay 
          playsInline 
          muted 
          className="w-full h-full object-cover scale-x-[-1]" // mirror effect
        />
      )}
      
      {/* Hidden canvas for taking snapshots without interrupting the video feed */}
      <canvas ref={canvasRef} style={{ display: "none" }} />
      
      {/* Optional: Indicator showing when tracking is actively sending frames */}
      {isAnswering && !cameraError && (
        <div className="absolute top-3 right-3 flex items-center gap-2 px-2 py-1 bg-black/60 rounded text-xs text-white backdrop-blur-sm">
          <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
          AI Analyzing
        </div>
      )}
    </div>
  );
}
```

## 🔄 Integration Steps

1. **Environment Variables**: Ensure `NEXT_PUBLIC_BACKEND_URL` is set in your frontend `.env.local` to point to the FastAPI server (e.g., `http://127.0.0.1:8000`).
2. **Mounting the Component**: Place `<LiveVideoTracker />` in your main Mock Interview UI layout.
3. **State Management**: 
   - Pass the `sessionId` returned from the `/interview/start` API.
   - Toss the `isAnswering` boolean state. Set it to `true` when the microphone is recording or the candidate is typing, and `false` when the AI avatar is speaking/loading.
   
The backend will automatically accumulate the frame insights in the MySQL database, and perfectly inject them into the final AI feedback report when the interview ends!
