import mediapipe as mp
import cv2
import numpy as np
import time
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

class PoseDetector:
    def __init__(self, min_detection_confidence=0.5, min_tracking_confidence=0.5):
        self.pose = mp_pose.Pose(
            min_detection_confidence=min_detection_confidence, 
            min_tracking_confidence=min_tracking_confidence,
            static_image_mode=False,
            smooth_landmarks=True
        )
        
    def calculate_angle(self, a, b, c):
        a = np.array(a)
        b = np.array(b)
        c = np.array(c)
        
        radians = np.arctan2(c[1]-b[1], c[0]-b[0]) - np.arctan2(a[1]-b[1], a[0]-b[0])
        angle = np.abs(radians*180.0/np.pi)
        
        if angle > 180.0:
            angle = 360 - angle
            
        return angle
    
    def detect_pose(self, frame):
        image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image.flags.writeable = False
        results = self.pose.process(image)

        image.flags.writeable = True
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        landmarks = None
        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark
            # Draw landmarks with custom styling
            mp_drawing.draw_landmarks(
                image, 
                results.pose_landmarks, 
                mp_pose.POSE_CONNECTIONS,
                mp_drawing.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2),
                mp_drawing.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2)
            )
        return image, landmarks
    
class BicepCurl:
    def __init__(self, detector: PoseDetector):
        self.detector = detector
        self.counter = 0
        self.stage = None
        self.angle_buffer = []  # For smoothing angle measurements
        self.min_angle_threshold = 50  # More strict minimum angle
        self.max_angle_threshold = 140  # More strict maximum angle
        self.confidence_threshold = 0.7  # Minimum landmark confidence
        
    def smooth_angle(self, angle, buffer_size=5):
        """Smooth angle measurements using a rolling average"""
        self.angle_buffer.append(angle)
        if len(self.angle_buffer) > buffer_size:
            self.angle_buffer.pop(0)
        return sum(self.angle_buffer) / len(self.angle_buffer)

    def is_pose_valid(self, landmarks):
        """Check if the pose has sufficient confidence for accurate tracking"""
        required_landmarks = [
            mp_pose.PoseLandmark.RIGHT_SHOULDER.value,
            mp_pose.PoseLandmark.RIGHT_ELBOW.value,
            mp_pose.PoseLandmark.RIGHT_WRIST.value
        ]
        
        for landmark_idx in required_landmarks:
            if landmarks[landmark_idx].visibility < self.confidence_threshold:
                return False
        return True

    def process(self, frame):
        """Process a frame and update bicep curl count"""
        image, landmarks = self.detector.detect_pose(frame)
        
        feedback = "Position yourself in frame"
        angle = 0
        current_stage = self.stage

        if landmarks and self.is_pose_valid(landmarks):
            # Get coordinates (RIGHT ARM) - convert to pixel coordinates
            h, w, _ = image.shape
            
            shoulder = [
                int(landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].x * w),
                int(landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].y * h)
            ]
            elbow = [
                int(landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value].x * w),
                int(landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value].y * h)
            ]
            wrist = [
                int(landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value].x * w),
                int(landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value].y * h)
            ]

            # Calculate and smooth angle
            raw_angle = self.detector.calculate_angle(shoulder, elbow, wrist)
            angle = self.smooth_angle(raw_angle)
            
            # Draw angle visualization
            cv2.circle(image, tuple(shoulder), 10, (255, 0, 0), -1)
            cv2.circle(image, tuple(elbow), 10, (0, 255, 0), -1)  
            cv2.circle(image, tuple(wrist), 10, (0, 0, 255), -1)
            
            # Draw lines between joints
            cv2.line(image, tuple(shoulder), tuple(elbow), (255, 255, 255), 3)
            cv2.line(image, tuple(elbow), tuple(wrist), (255, 255, 255), 3)
            
            # Display angle at elbow
            cv2.putText(image, f'{int(angle)}°', 
                       (elbow[0] - 30, elbow[1] - 20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

            # Improved curl logic with better thresholds
            if angle > self.max_angle_threshold:
                if self.stage != "down":
                    self.stage = "down"
                    current_stage = "down"
                feedback = "Lower your arm more"
                
            elif angle < self.min_angle_threshold and self.stage == "down":
                if self.stage != "up":
                    self.stage = "up"
                    current_stage = "up"
                    self.counter += 1
                    feedback = "Great rep! Lower your arm"
                else:
                    feedback = "Hold the curl"
                    
            elif self.min_angle_threshold <= angle <= self.max_angle_threshold:
                if self.stage == "down":
                    feedback = "Keep curling up"
                elif self.stage == "up":
                    feedback = "Lower your arm slowly"
                else:
                    feedback = "Start with arm extended"
            else:
                feedback = f"Current angle: {int(angle)}°"

        # Add exercise info overlay
        cv2.rectangle(image, (10, 10), (300, 120), (0, 0, 0), -1)
        cv2.putText(image, f'Bicep Curls: {self.counter}', (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(image, f'Stage: {current_stage or "ready"}', (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(image, f'Angle: {int(angle)}°', (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return image, self.counter, feedback, int(angle), current_stage or "ready"
class Squat:
    def __init__(self, detector):
        self.detector = detector
        self.counter = 0
        self.stage = None
        self.angle_buffer = []  # For smoothing angle measurements
        self.min_angle_threshold = 70   # Minimum knee angle for squat down
        self.max_angle_threshold = 160  # Maximum knee angle for standing up
        self.confidence_threshold = 0.7  # Minimum landmark confidence
        
    def smooth_angle(self, angle, buffer_size=5):
        """Smooth angle measurements using a rolling average"""
        self.angle_buffer.append(angle)
        if len(self.angle_buffer) > buffer_size:
            self.angle_buffer.pop(0)
        return sum(self.angle_buffer) / len(self.angle_buffer)

    def is_pose_valid(self, landmarks):
        """Check if the pose has sufficient confidence for accurate tracking"""
        required_landmarks = [
            mp_pose.PoseLandmark.RIGHT_HIP.value,
            mp_pose.PoseLandmark.RIGHT_KNEE.value,
            mp_pose.PoseLandmark.RIGHT_ANKLE.value
        ]
        
        for landmark_idx in required_landmarks:
            if landmarks[landmark_idx].visibility < self.confidence_threshold:
                return False
        return True

    def process(self, frame):
        """Process a frame and update squat count"""
        image, landmarks = self.detector.detect_pose(frame)
        
        feedback = "Position yourself in frame"
        angle = 0
        current_stage = self.stage

        if landmarks and self.is_pose_valid(landmarks):
            # Get coordinates (RIGHT LEG) - convert to pixel coordinates
            h, w, _ = image.shape
            
            hip = [
                int(landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value].x * w),
                int(landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value].y * h)
            ]
            knee = [
                int(landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value].x * w),
                int(landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value].y * h)
            ]
            ankle = [
                int(landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value].x * w),
                int(landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value].y * h)
            ]

            # Calculate and smooth angle
            raw_angle = self.detector.calculate_angle(hip, knee, ankle)
            angle = self.smooth_angle(raw_angle)
            
            # Draw angle visualization
            cv2.circle(image, tuple(hip), 10, (255, 0, 0), -1)
            cv2.circle(image, tuple(knee), 10, (0, 255, 0), -1)  
            cv2.circle(image, tuple(ankle), 10, (0, 0, 255), -1)
            
            # Draw lines between joints
            cv2.line(image, tuple(hip), tuple(knee), (255, 255, 255), 3)
            cv2.line(image, tuple(knee), tuple(ankle), (255, 255, 255), 3)
            
            # Display angle at knee
            cv2.putText(image, f'{int(angle)}°', 
                       (knee[0] - 30, knee[1] - 20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

            # Squat logic
            if angle > self.max_angle_threshold:
                if self.stage != "up":
                    self.stage = "up"
                    current_stage = "up"
                feedback = "Standing position"
                
            elif angle < self.min_angle_threshold and self.stage == "up":
                if self.stage != "down":
                    self.stage = "down"
                    current_stage = "down"
                    self.counter += 1
                    feedback = "Great squat! Stand up"
                else:
                    feedback = "Hold the squat"
                    
            elif self.min_angle_threshold <= angle <= self.max_angle_threshold:
                if self.stage == "up":
                    feedback = "Keep squatting down"
                elif self.stage == "down":
                    feedback = "Stand up slowly"
                else:
                    feedback = "Start standing up"
            else:
                feedback = f"Current angle: {int(angle)}°"

        # Add exercise info overlay
        cv2.rectangle(image, (10, 10), (300, 120), (0, 0, 0), -1)
        cv2.putText(image, f'Squats: {self.counter}', (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(image, f'Stage: {current_stage or "ready"}', (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(image, f'Angle: {int(angle)}°', (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return image, self.counter, feedback, int(angle), current_stage or "ready"


class Pushup:
    def __init__(self, detector):
        self.detector = detector
        self.counter = 0
        self.stage = None
        self.angle_buffer = []  # For smoothing angle measurements
        self.min_angle_threshold = 70   # Minimum elbow angle for pushup down
        self.max_angle_threshold = 160  # Maximum elbow angle for pushup up
        self.confidence_threshold = 0.7  # Minimum landmark confidence
        
    def smooth_angle(self, angle, buffer_size=5):
        """Smooth angle measurements using a rolling average"""
        self.angle_buffer.append(angle)
        if len(self.angle_buffer) > buffer_size:
            self.angle_buffer.pop(0)
        return sum(self.angle_buffer) / len(self.angle_buffer)

    def is_pose_valid(self, landmarks):
        """Check if the pose has sufficient confidence for accurate tracking"""
        required_landmarks = [
            mp_pose.PoseLandmark.RIGHT_SHOULDER.value,
            mp_pose.PoseLandmark.RIGHT_ELBOW.value,
            mp_pose.PoseLandmark.RIGHT_WRIST.value
        ]
        
        for landmark_idx in required_landmarks:
            if landmarks[landmark_idx].visibility < self.confidence_threshold:
                return False
        return True

    def process(self, frame):
        """Process a frame and update pushup count"""
        image, landmarks = self.detector.detect_pose(frame)
        
        feedback = "Position yourself in frame"
        angle = 0
        current_stage = self.stage

        if landmarks and self.is_pose_valid(landmarks):
            # Get coordinates (RIGHT ARM) - convert to pixel coordinates
            h, w, _ = image.shape
            
            shoulder = [
                int(landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].x * w),
                int(landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].y * h)
            ]
            elbow = [
                int(landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value].x * w),
                int(landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value].y * h)
            ]
            wrist = [
                int(landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value].x * w),
                int(landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value].y * h)
            ]

            # Calculate and smooth angle
            raw_angle = self.detector.calculate_angle(shoulder, elbow, wrist)
            angle = self.smooth_angle(raw_angle)
            
            # Draw angle visualization
            cv2.circle(image, tuple(shoulder), 10, (255, 0, 0), -1)
            cv2.circle(image, tuple(elbow), 10, (0, 255, 0), -1)  
            cv2.circle(image, tuple(wrist), 10, (0, 0, 255), -1)
            
            # Draw lines between joints
            cv2.line(image, tuple(shoulder), tuple(elbow), (255, 255, 255), 3)
            cv2.line(image, tuple(elbow), tuple(wrist), (255, 255, 255), 3)
            
            # Display angle at elbow
            cv2.putText(image, f'{int(angle)}°', 
                       (elbow[0] - 30, elbow[1] - 20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

            # Pushup logic
            if angle > self.max_angle_threshold:
                if self.stage != "up":
                    self.stage = "up"
                    current_stage = "up"
                feedback = "Plank position"
                
            elif angle < self.min_angle_threshold and self.stage == "up":
                if self.stage != "down":
                    self.stage = "down"
                    current_stage = "down"
                    self.counter += 1
                    feedback = "Great pushup! Push back up"
                else:
                    feedback = "Hold the bottom position"
                    
            elif self.min_angle_threshold <= angle <= self.max_angle_threshold:
                if self.stage == "up":
                    feedback = "Keep lowering down"
                elif self.stage == "down":
                    feedback = "Push back up"
                else:
                    feedback = "Start in plank position"
            else:
                feedback = f"Current angle: {int(angle)}°"

        # Add exercise info overlay
        cv2.rectangle(image, (10, 10), (300, 120), (0, 0, 0), -1)
        cv2.putText(image, f'Pushups: {self.counter}', (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(image, f'Stage: {current_stage or "ready"}', (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(image, f'Angle: {int(angle)}°', (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return image, self.counter, feedback, int(angle), current_stage or "ready"


class Plank:
    def __init__(self, detector):
        self.detector = detector
        self.counter = 0  # This will represent time held in seconds
        self.stage = None
        self.angle_buffer = []  # For smoothing angle measurements
        self.min_hip_angle = 160  # Minimum hip angle for proper plank
        self.max_hip_angle = 190  # Maximum hip angle for proper plank
        self.confidence_threshold = 0.7  # Minimum landmark confidence
        self.start_time = None
        self.total_time = 0
        self.is_in_plank = False
        
    def smooth_angle(self, angle, buffer_size=5):
        """Smooth angle measurements using a rolling average"""
        self.angle_buffer.append(angle)
        if len(self.angle_buffer) > buffer_size:
            self.angle_buffer.pop(0)
        return sum(self.angle_buffer) / len(self.angle_buffer)

    def is_pose_valid(self, landmarks):
        """Check if the pose has sufficient confidence for accurate tracking"""
        required_landmarks = [
            mp_pose.PoseLandmark.RIGHT_SHOULDER.value,
            mp_pose.PoseLandmark.RIGHT_HIP.value,
            mp_pose.PoseLandmark.RIGHT_KNEE.value
        ]
        
        for landmark_idx in required_landmarks:
            if landmarks[landmark_idx].visibility < self.confidence_threshold:
                return False
        return True

    def process(self, frame):
        """Process a frame and update plank time"""
        image, landmarks = self.detector.detect_pose(frame)
        
        feedback = "Position yourself in frame"
        angle = 0
        current_stage = self.stage

        if landmarks and self.is_pose_valid(landmarks):
            # Get coordinates (BODY ALIGNMENT) - convert to pixel coordinates
            h, w, _ = image.shape
            
            shoulder = [
                int(landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].x * w),
                int(landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value].y * h)
            ]
            hip = [
                int(landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value].x * w),
                int(landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value].y * h)
            ]
            knee = [
                int(landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value].x * w),
                int(landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value].y * h)
            ]

            # Calculate and smooth hip angle (body alignment)
            raw_angle = self.detector.calculate_angle(shoulder, hip, knee)
            angle = self.smooth_angle(raw_angle)
            
            # Draw angle visualization
            cv2.circle(image, tuple(shoulder), 10, (255, 0, 0), -1)
            cv2.circle(image, tuple(hip), 10, (0, 255, 0), -1)  
            cv2.circle(image, tuple(knee), 10, (0, 0, 255), -1)
            
            # Draw lines between joints
            cv2.line(image, tuple(shoulder), tuple(hip), (255, 255, 255), 3)
            cv2.line(image, tuple(hip), tuple(knee), (255, 255, 255), 3)
            
            # Display angle at hip
            cv2.putText(image, f'{int(angle)}°', 
                       (hip[0] - 30, hip[1] - 20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

            # Plank logic - check if body is straight
            if self.min_hip_angle <= angle <= self.max_hip_angle:
                if not self.is_in_plank:
                    self.is_in_plank = True
                    self.start_time = time.time()
                    self.stage = "holding"
                    current_stage = "holding"
                    feedback = "Perfect plank! Hold it!"
                else:
                    # Update time
                    if self.start_time:
                        current_time = time.time()
                        self.counter = int(current_time - self.start_time + self.total_time)
                    feedback = f"Great form! Hold for {self.counter}s"
                    current_stage = "holding"
                    
            else:
                if self.is_in_plank:
                    # Was in plank, now out - save the time
                    if self.start_time:
                        self.total_time += time.time() - self.start_time
                        self.start_time = None
                    self.is_in_plank = False
                    
                self.stage = "adjusting"
                current_stage = "adjusting"
                
                if angle < self.min_hip_angle:
                    feedback = "Lower your hips - keep body straight"
                elif angle > self.max_hip_angle:
                    feedback = "Raise your hips - keep body straight"
                else:
                    feedback = "Get into plank position"

        else:
            # No valid pose detected
            if self.is_in_plank:
                if self.start_time:
                    self.total_time += time.time() - self.start_time
                    self.start_time = None
                self.is_in_plank = False

        # Add exercise info overlay
        cv2.rectangle(image, (10, 10), (300, 120), (0, 0, 0), -1)
        cv2.putText(image, f'Plank Time: {self.counter}s', (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(image, f'Stage: {current_stage or "ready"}', (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(image, f'Angle: {int(angle)}°', (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return image, self.counter, feedback, int(angle), current_stage or "ready"