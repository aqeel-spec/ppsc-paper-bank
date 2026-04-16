import asyncio
import websockets
import json
import base64

# A tiny 1x1 black pixel base64 jpeg to trigger the endpoint safely
DUMMY_B64 = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="

async def test_ws():
    uri = "ws://127.0.0.1:8000/interview/ws/video-stream/test_session_123"
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected! Sending frame...")
            payload = {
                "action": "analyze_frame",
                "image_b64": f"data:image/jpeg;base64,{DUMMY_B64}"
            }
            await websocket.send(json.dumps(payload))
            print("Frame sent. The server should process it and save to DB.")
            print("Check your FastAPI terminal for 'Vision Insight' logs.")
            
            # Keep open for a moment to let the server process
            await asyncio.sleep(5)
            print("Closing connection.")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
