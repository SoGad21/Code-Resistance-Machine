#include <HX711_ADC.h>

// --- ตั้งค่า PIN ---
int RPWM_Output = 6;
int LPWM_Output = 7;
int R_EN = 12;
int L_EN = 13;

const int HX711_dout = 4;
const int HX711_sck = 5;

// --- ตั้งค่าเวลาและมอเตอร์ (รับคำสั่งอัปเดตจาก Python ได้) ---
unsigned long testDuration = 3500;      // เวลาทดสอบเริ่มต้น (มิลลิวินาที)
int motorSpeed = 220;                   // ความเร็วมอเตอร์ดึงเริ่มต้น (0-255)
const unsigned long PAUSE_TIME = 400;   // เวลาพักก่อนกลับ (0.4 วินาที)

// --- ตัวแปรระบบ ---
HX711_ADC LoadCell(HX711_dout, HX711_sck);
unsigned long stateStartTime = 0;
unsigned long lastSerialTime = 0;

// สถานะการทำงาน (State Machine)
enum MachineState { IDLE, FORWARDING, PAUSING, REVERSING, FINISHED, MANUAL };
MachineState currentState = IDLE;

void setup() {
  Serial.begin(57600); 
  
  pinMode(RPWM_Output, OUTPUT);
  pinMode(LPWM_Output, OUTPUT);
  pinMode(R_EN, OUTPUT);
  pinMode(L_EN, OUTPUT);

  // เปิดใช้งาน Driver
  digitalWrite(R_EN, HIGH);
  digitalWrite(L_EN, HIGH);

  // Setup Load Cell
  LoadCell.begin();
  LoadCell.start(2000, true);
  if (LoadCell.getTareTimeoutFlag()) {
    Serial.println("ERROR: Check Load Cell Wiring");
    while (1);
  }
  LoadCell.setCalFactor(1.0); // ค่า Calibrate จะถูกเขียนทับจาก Python อัตโนมัติ
  Serial.println("SYSTEM_READY");
}

void loop() {
  LoadCell.update(); // อ่านค่า Load Cell ตลอดเวลา
  unsigned long currentMillis = millis();

  // --- 1. ส่วนรับคำสั่งจาก Python ---
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    
    if (cmd == 'S' && currentState == IDLE) {
      currentState = FORWARDING;
      stateStartTime = currentMillis;
      LoadCell.tareNoDelay(); 
      Serial.println("STATUS:STARTED");
    }
    else if (cmd == 'X') {
      stopMotor();
      currentState = IDLE;
      Serial.println("STATUS:STOPPED");
    }
    else if (cmd == 'T' && currentState == IDLE) {
      LoadCell.tareNoDelay();
    }
    else if (cmd == 'F') { 
      stopMotor();
      analogWrite(RPWM_Output, motorSpeed); 
      analogWrite(LPWM_Output, 0);
      currentState = MANUAL; 
    }
    else if (cmd == 'B') { 
      stopMotor();
      analogWrite(RPWM_Output, 0);
      analogWrite(LPWM_Output, 220);
      currentState = MANUAL; 
    }
    // --- รับค่า Setting จาก Python (ดักจับ Error ให้ด้วย) ---
    else if (cmd == 'P') { 
      int val = Serial.parseInt();
      if (val > 0 && val <= 255) motorSpeed = val;
    }
    else if (cmd == 'D') { 
      long val = Serial.parseInt();
      if (val > 0) testDuration = val;
    }
    else if (cmd == 'C') { 
      float newCal = Serial.parseFloat(); 
      if (newCal > 0) LoadCell.setCalFactor(newCal); 
    }
  }

  // --- 2. ส่วนควบคุมการทำงาน (State Machine) ---
  switch (currentState) {
    
    case IDLE:
      stopMotor();
      if (currentMillis - lastSerialTime > 200) {
        Serial.print("PREVIEW:");
        Serial.println(LoadCell.getData());
        lastSerialTime = currentMillis;
      }
      break;

    case FORWARDING:
      analogWrite(RPWM_Output, motorSpeed);
      analogWrite(LPWM_Output, 0); 

      if (currentMillis - lastSerialTime > 50) {
        Serial.print("DATA:");
        Serial.println(LoadCell.getData());
        lastSerialTime = currentMillis;
      }

      if (currentMillis - stateStartTime >= testDuration) {
        stopMotor();
        currentState = PAUSING;
        stateStartTime = currentMillis;
      }
      break;

    case PAUSING:
      stopMotor();
      if (currentMillis - stateStartTime >= PAUSE_TIME) {
        currentState = REVERSING;
        stateStartTime = currentMillis;
        Serial.println("STATUS:REVERSING"); // บอก Python ให้เปลี่ยนปุ่มเป็นสีฟ้า
      }
      break;

    case REVERSING: { // <--- เพิ่มวงเล็บปีกกาเพื่อป้องกัน Error
      analogWrite(RPWM_Output, 0); 
      analogWrite(LPWM_Output, 220); // ถอยกลับด้วยความเร็วสูงสุดเสมอ

      // บังคับคำนวณเป็นแบบ 32-bit ป้องกันอาการตัวเลขล้น (Integer Overflow)
      unsigned long returnDuration = ((unsigned long)testDuration * (unsigned long)motorSpeed) / 220;

      if (currentMillis - stateStartTime >= returnDuration) {
        stopMotor();
        currentState = FINISHED; 
      }
      break;
    } // <--- ปิดวงเล็บปีกกา

    case FINISHED:
      stopMotor();
      Serial.println("STATUS:FINISHED"); // ส่งสัญญาณบอก Python ให้เซฟข้อมูลและแสดงผล
      currentState = IDLE;
      break;

    case MANUAL:
      // รันค้างไว้จนกว่าจะได้รับคำสั่ง X ให้หยุด
      break;
  }
}

void stopMotor() {
  analogWrite(RPWM_Output, 0);
  analogWrite(LPWM_Output, 0);
}