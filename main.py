import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import base64
from excersises import PoseDetector, BicepCurl, Squat, Pushup, Plank

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Server running"}

detector = PoseDetector()
bicep = BicepCurl(detector)
squat = Squat(detector)
pushup = Pushup(detector)
plank = Plank(detector)

@app.websocket("/ws/{exercise}")
async def websocket_endpoint(websocket: WebSocket, exercise: str):
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            if not data:
                continue

            try:
                if data.startswith('data:image'):
                    data = data.split(',')[1]
                
                img_data = base64.b64decode(data)
                nparr = np.frombuffer(img_data, np.uint8)
                if nparr.size == 0:
                    continue
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if frame is None:
                    continue
            except:
                continue
            
            if exercise == "biceps":
                processed_frame, reps, feedback, angle, stage = bicep.process(frame)
            elif exercise == "squats":
                processed_frame, reps, feedback, angle, stage = squat.process(frame)
            elif exercise == "pushups":
                processed_frame, reps, feedback, angle, stage = pushup.process(frame)
            elif exercise == "plank":
                processed_frame, reps, feedback, angle, stage = plank.process(frame)
            else:
                continue

            try:
                _, buffer = cv2.imencode('.jpg', processed_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                processed_frame_b64 = base64.b64encode(buffer).decode('utf-8')
            except:
                processed_frame_b64 = None

            response = {
                "exercise": exercise,
                "reps": reps,
                "feedback": feedback,
                "angle": angle,
                "stage": stage,
            }
            
            if processed_frame_b64:
                response["processed_frame"] = processed_frame_b64

            await websocket.send_json(response)

    except WebSocketDisconnect:
        pass
    except:
        pass

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)