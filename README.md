# ARAISE workout backend

This FastAPI service turns a stream of workout images into rep counts, plank hold time, and form feedback. A client selects an exercise in the WebSocket URL and sends one image at a time. For each processed frame, the server returns the joint angle, movement stage, a coaching cue, and an annotated image when available.

The [ARAISE web app](https://github.com/Ruthwik000/Arasie) provides the workout interface. Meal-photo analysis runs in the separate [food backend](https://github.com/Ruthwik000/food_araise).

## Architecture

The browser and server each run pose detection. The WebSocket route selects the exercise, and the format of each text message determines whether the server can process it.

```mermaid
sequenceDiagram
    box Frontend
        participant C as Browser client
    end
    box Backend
        participant W as FastAPI WebSocket
        participant T as Exercise tracker
        participant P as MediaPipe Pose
    end
    C->>W: Connect to /ws/{exercise}
    W-->>C: Accept connection
    alt React workout screen
        C->>C: Detect joints and map to canvas pixels
        C->>W: JSON text with joint coordinates
        W->>W: Image decode fails, skip message
    else Image client or README test
        C->>W: Base64 image text
        W->>W: Decode bytes into an OpenCV BGR frame
        W->>T: Call process(frame) for the selected exercise
        T->>P: Convert BGR to RGB and infer landmarks
        P-->>T: Landmarks and visibility scores
        T->>T: Check visibility, smooth angle, update state
        T-->>W: Annotated frame, count, feedback, angle, stage
        W-->>C: JSON metrics and optional base64 JPEG
    end
```

**Frontend.** In `PoseAnalyzer.jsx`, the camera client calls MediaPipe's `detectForVideo` through `poseDetection.js`. It converts the selected joints to canvas pixel pairs such as `right_elbow: [x, y]`. The WebSocket client serializes `exercise`, `coordinates`, `timestamp`, `planId`, and `level` as JSON. The screen listens for rep counts, stages, joint angles, and feedback, which it can also read aloud.

**WebSocket contract.** For each message, FastAPI calls `receive_text()`, strips the optional image data URL prefix, then passes the payload through `base64.b64decode`, `np.frombuffer(..., np.uint8)`, and `cv2.imdecode`. Coordinate JSON fails this decode path, so the React client receives no reply for those messages. The [one-frame test](#try-one-frame) exercises the accepted image path. After tracking, `send_json()` returns the metrics and, when encoding succeeds, `processed_frame` as a base64 JPEG at quality 70. See [main.py](./main.py).

**Tracking and state.** The URL selects a process-wide `BicepCurl`, `Squat`, `Pushup`, or `Plank` instance. All four share one `PoseDetector`. When the three required right-side landmarks each have visibility of at least 0.7, the tracker computes the 2D joint angle between adjacent limb segments, folds it into 0–180°, and averages up to five valid readings. Rep trackers count a threshold crossing only after the preceding stage has been reached. The plank tracker accumulates elapsed hold time. The handler runs inference synchronously before sending the response and reading the next message on that connection. See [excersises.py](./excersises.py).

## What each exercise measures

Use one of the four paths below. The server accepts connections for other exercise names but skips their frames without replying.

| WebSocket path | Joint | When the result changes |
| --- | --- | --- |
| `/ws/biceps` | Right elbow | Extending past 140° sets the stage to `down`. Curling below 50° then counts one rep and sets it to `up`. |
| `/ws/squats` | Right knee | Standing past 160° sets the stage to `up`. Lowering below 70° then counts one squat. |
| `/ws/pushups` | Right elbow | Straightening past 160° sets the stage to `up`. Lowering below 70° then counts one push-up. |
| `/ws/plank` | Right hip | A smoothed angle of at least 160° starts or resumes the hold. Moving out of range or losing the pose pauses timing. The result accumulates across holds. |

For the three rep exercises, the starting stage must be reached again before another rep can count. For a plank, `reps` contains accumulated whole seconds. When the required joints are missing or poorly visible, the response reports an angle of zero and the cue `Position yourself in frame`.

## Run locally

Use Python 3.11. From the repository root on Windows, run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Open `http://127.0.0.1:8000/`. The health check returns `{"message":"Server running"}`. Set `PORT` to change the default port of 8000. The repository also includes the [Render deployment configuration](./render.yaml).

## Try one frame

With the server running, open the health-check page and paste this into the browser console. It creates a blank image and sends it as a WebSocket text message, so the example works without camera permission.

```javascript
const frame = document.createElement("canvas");
frame.width = 320;
frame.height = 240;
const socket = new WebSocket("ws://127.0.0.1:8000/ws/squats");
socket.onopen = () => socket.send(frame.toDataURL("image/jpeg"));
socket.onmessage = ({ data }) => {
  const { processed_frame, ...metrics } = JSON.parse(data);
  console.log(metrics);
  socket.close();
};
```

On a fresh server, the expected metrics for that blank frame are:

```json
{"exercise":"squats","reps":0,"feedback":"Position yourself in frame","angle":0,"stage":"ready"}
```

For live tracking, draw the current video frame onto the canvas before sending it and keep the socket open across frames. The server accepts raw base64 text or an image data URL. The optional `processed_frame` response field contains base64 JPEG data. Prefix it with `data:image/jpeg;base64,` to display it in an image element.

## Session state

Each server process creates one detector and one tracker per exercise. Clients using the same exercise share its counter, stage, and angle history. Reconnecting to the same process keeps that state. Restarting the process clears it. The handler does not use the frontend's `user_id` query parameter to isolate workouts.
