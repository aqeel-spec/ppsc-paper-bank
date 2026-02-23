# Live Video Tracking Architecture: AI Psychological Expert

This guide details the end-to-end architecture to stream live video from your Next.js frontend to the FastAPI backend, process the frames using a Vision LLM (like GPT-4o via GitHub Models), and have the AI act as a Psychological Specialist to analyze the candidate's gestures, eye contact, and body language during the interview.

---

## 🏗 High-Level Architecture Flow

1. **Frontend (Next.js)**: The `LiveVideoTracker` grabs the user's webcam. While they are answering a question, a hidden HTML `<canvas>` captures a frame (screenshot) every 2-3 seconds, converts it to a compressed `base64` JPEG, and sends it to the backend via a secure `WebSocket` connection.
2. **Backend (FastAPI)**: A dedicated WebSocket endpoint receives these `base64` frames in real-time.
3. **Vision Processing (LiteLLM)**: The backend batches 2-3 frames together and sends them to the OpenAI Vision Model (`gpt-4o` or `gpt-4o-mini` on GitHub Models) with a specialized "Psychological Expert" prompt.
4. **Database Storage**: The behavioral observations (e.g., "candidate is making good eye contact", "nervous fidgeting detected") are saved as metadata to the current `InterviewSession`.
5. **Final Evaluation**: When the interview concludes, these aggregate behavioral notes are injected into the final feedback agent's prompt, influencing the "Cultural Fit / Behavioral" score.

---

## 💻 1. Frontend Implementation (Next.js)

Update your `LiveVideoTracker` component to connect to a WebSocket and periodically send frames while the video is enabled.

```typescript
// src/components/interview/live-video-tracker.tsx
import { useEffect, useRef, useState, useCallback } from "react";

export function LiveVideoTracker({ sessionId, isAnswering, ...props }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Connect to the Analysis WebSocket
  useEffect(() => {
    if (!sessionId) return;
    const wsUrl = `ws://127.0.0.1:8000/ws/video-stream/${sessionId}`;
    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => console.log("Connected to AI Behavioral Analysis");
    wsRef.current.onerror = (err) => console.error("Behavioral WS Error:", err);

    return () => wsRef.current?.close();
  }, [sessionId]);

  // Capture & Send Frame Loop
  useEffect(() => {
    let intervalId: NodeJS.Timeout;

    const captureFrame = () => {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!video || !canvas || !wsRef.current) return;
      if (wsRef.current.readyState !== WebSocket.OPEN) return;

      const context = canvas.getContext("2d");
      if (context) {
        // Draw the current video frame to the canvas (low resolution for speed)
        canvas.width = 320; 
        canvas.height = 240;
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        // Convert to highly-compressed JPEG base64 (quality 0.6)
        const base64Data = canvas.toDataURL("image/jpeg", 0.6);
        
        wsRef.current.send(JSON.stringify({
          action: "analyze_frame",
          image_b64: base64Data
        }));
      }
    };

    // Only send frames if the camera is ON and the candidate is actively answering
    if (isAnswering && videoRef.current) {
      intervalId = setInterval(captureFrame, 3000); // 1 frame every 3 seconds
    }

    return () => clearInterval(intervalId);
  }, [isAnswering]);

  return (
    <div>
      <video ref={videoRef} autoPlay playsInline muted />
      {/* Hidden canvas for taking snapshots without interrupting the video feed */}
      <canvas ref={canvasRef} style={{ display: "none" }} />
    </div>
  );
}
```

---

## ⚙️ 2. Backend Implementation (FastAPI)

Create a WebSocket route inside your FastAPI app (`mock_interview.py` or a dedicated `ws_routes.py`) to receive the base64 frames and analyze them.

```python
import base64
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from litellm import completion

router = APIRouter()

# Store observations in a temporary dictionary or memory (Production: save to DB)
SESSION_OBSERVATIONS = {}

PSYCHOLOGIST_PROMPT = """You are Ms. Fatima Noor, a highly trained PPSC Behavioral & Psychological Expert.
Analyze the provided images of the candidate during their interview response.
Note everything:
1. Eye contact (Are they looking at the camera/panel?)
2. Posture (Slouching, confident, rigid?)
3. Nervousness (Fidgeting, touching face, sweating?)
4. Professional appearance.

Provide a concise, 1-2 sentence behavioral summary of what you observe in this timeframe. Be objective.
Format: 'Behavior: [Your observation]'.
"""

@router.websocket("/ws/video-stream/{session_id}")
async def video_analysis_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    if session_id not in SESSION_OBSERVATIONS:
        SESSION_OBSERVATIONS[session_id] = []
        
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("action") == "analyze_frame":
                b64_img = data.get("image_b64")
                
                # Strip the prefix 'data:image/jpeg;base64,'
                if "," in b64_img:
                    b64_img = b64_img.split(",")[1]
                
                # Call GitHub Models / OpenAI Vision API using LiteLLM
                # (Ensure your current model supports Vision, e.g., gpt-4o or gpt-4o-mini)
                try:
                    response = completion(
                        model="github/gpt-4o", # Or whatever your vision model endpoint is named
                        messages=[
                            {"role": "system", "content": PSYCHOLOGIST_PROMPT},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "Analyze this video frame of the candidate."},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                                ]
                            }
                        ],
                        max_tokens=60
                    )
                    
                    insight = response.choices[0].message.content
                    print(f"[{session_id} - Vision Insight]: {insight}")
                    
                    # Store this observation for the final report
                    SESSION_OBSERVATIONS[session_id].append(insight)
                    
                except Exception as e:
                    print(f"Vision API Error: {str(e)}")
                    
    except WebSocketDisconnect:
        print(f"Client {session_id} disconnected from Live Video Tracking.")
```

---

## 📊 3. Feedback Integration (The Final Step)

When the candidate finishes the interview and you click "Get Feedback", all the behavioral notes accumulated by the Vision model need to be passed to the Final Grader.

Modify your `/feedback` endpoint in `mock_interview.py`:

```python
@router.post("/feedback")
async def get_feedback(payload: FeedbackRequest, db: Session = Depends(get_session)):
    
    # ... Fetch existing text conversation from DB ...
    
    # Fetch behavioral notes from memory
    behavioral_notes = SESSION_OBSERVATIONS.get(payload.session_id, [])
    
    combined_notes = "\n- ".join(behavioral_notes[-15:]) # Grab the latest 15 observations safely
    
    vision_context = f"\n\n### Psychological Expert (Vision) Notes on Body Language:\n- {combined_notes}" if combined_notes else ""
    
    prompt = (
        "You are an interview performance analyst.\n"
        "Given the full conversation transcript AND the live behavioral notes from the Psychologist Avatar, produce a detailed feedback report.\n"
        "Make sure to specifically comment on their posture, eye contact, and confidence in the 'Strengths' or 'Areas for Improvement' based on the vision notes."
        f"{vision_context}"
    )
    
    # ... Send to standard feedback LLM agent and return ...
```

---

## 🛠 Required Optimizations

1. **Rate Limiting**: GitHub Models (and OpenAI API) have strict requests-per-minute limits. Do NOT send a frame every second. Instead:
   - Client-side throttling: `setInterval(captureFrame, 5000)` (Once every 5 seconds).
   - Only capture frames when the user is speaking/typing, not when the AI is talking.
2. **Resolution**: Always keep the canvas size small (`320x240`). Vision models downsample large images anyway; sending a 4K frame just wastes your bandwidth and slows the WebSocket.
3. **Database Integration**: Instead of the in-memory `SESSION_OBSERVATIONS` dictionary, add a new table `InterviewBehaviorLog (session_id, timestamp, observation_text)` to persist these notes securely across server restarts.
