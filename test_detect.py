import cv2
from detector_engine import GarbageDetector

detector = GarbageDetector("models/best.pt", conf=0.35)

# Replace with your mobile IP and port
cap = cv2.VideoCapture("http://192.168.100.29:8080/video?dummy=param.mjpg")
if not cap.isOpened():
    print("Cannot open stream, check IP/port/phone is on same WiFi")
else:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Frame read failed")
            break
        dets = detector.detect(frame)
        for d in dets:
            x1, y1, x2, y2 = d['box']
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"{d['cls']} {d['conf']:.2f}", (x1, y1-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        cv2.imshow("E-Safai Test", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()