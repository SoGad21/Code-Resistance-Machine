#include <HX711_ADC.h>

// --- ตั้งค่า PIN ---
int RPWM_Output = 6;
int LPWM_Output = 7;
int R_EN = 12;
int L_EN = 13;

const int HX711_dout = 4;
const int HX711_sck = 5;

// --- ตั้งค่าเวลา (Configuration) ---
// *สำคัญ* ปรับเวลาตรงนี้ให้มากกว่าเวลาที่มอเตอร์วิ่งจริงเล็กน้อย
const unsigned long RUN_TIMEOUT = 12000; // 12 วินาที (เวลาหมุนไป หรือ กลับ)
const unsigned long PAUSE_TIME = 2000;   // 2 วินาที (เวลาพักก่อนกลับ)

// --- ตัวแปรระบบ ---
HX711_ADC LoadCell(HX711_dout, HX711_sck);
unsigned long stateStartTime = 0;
unsigned long lastSerialTime = 0;

// สถานะการทำงาน (State Machine)
enum MachineState { IDLE, FORWARDING, PAUSING, REVERSING, FINISHED };
MachineState currentState = IDLE;

void setup() {
  Serial.begin(57600); // ใช้ Baudrate เดิมของคุณ
  
  pinMode(RPWM_Output, OUTPUT);
  pinMode(LPWM_Output, OUTPUT);
  pinMode(R_EN, OUTPUT);
  pinMode(L_EN, OUTPUT);

  // เปิดใช้งาน Driver
  digitalWrite(R_EN, HIGH);
  digitalWrite(L_EN, HIGH);

  // Setup Load Cell
  LoadCell.begin();
  LoadCell.start(2000, true); // Tare เมื่อเริ่ม
  if (LoadCell.getTareTimeoutFlag()) {
    Serial.println("ERROR: Check Load Cell Wiring");
    while (1);
  }
  LoadCell.setCalFactor(1.0); // **อย่าลืมใส่ค่า Calibrate จริงของคุณที่นี่**
  Serial.println("SYSTEM_READY");
}

void loop() {
  LoadCell.update(); // อ่านค่า Load Cell ตลอดเวลา
  unsigned long currentMillis = millis();

  // --- 1. ส่วนรับคำสั่งจาก Python ---
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    
    // คำสั่ง Start Test
    if (cmd == 'S' && currentState == IDLE) {
      currentState = FORWARDING;
      stateStartTime = currentMillis;
      LoadCell.tareNoDelay(); // Tare อัตโนมัติก่อนเริ่ม
      Serial.println("STATUS:STARTED");
    }
    // คำสั่ง Emergency Stop
    else if (cmd == 'X') {
      stopMotor();
      currentState = IDLE;
      Serial.println("STATUS:STOPPED");
    }
    // คำสั่ง Tare (กดได้เฉพาะตอนว่าง)
    else if (cmd == 'T' && currentState == IDLE) {
      LoadCell.tareNoDelay();
      Serial.println("STATUS:TARED");
    }
  }

  // --- 2. ส่วนควบคุมการทำงาน (State Machine) ---
  switch (currentState) {
    
    case IDLE:
      stopMotor();
      // ส่งค่าแบบ Preview (ส่งช้าๆ ไม่ต้องรัว)
      if (currentMillis - lastSerialTime > 200) {
        Serial.print("PREVIEW:");
        Serial.println(LoadCell.getData());
        lastSerialTime = currentMillis;
      }
      break;

    case FORWARDING:
      // สั่งมอเตอร์เดินหน้า
      analogWrite(RPWM_Output, 0);
      analogWrite(LPWM_Output, 220); // *ปรับความเร็วตรงนี้*

      // ส่งข้อมูลกราฟ (ส่งรัวๆ)
      if (currentMillis - lastSerialTime > 50) {
        Serial.print("DATA:");
        Serial.println(LoadCell.getData());
        lastSerialTime = currentMillis;
      }

      // เช็คเวลา
      if (currentMillis - stateStartTime >= RUN_TIMEOUT) {
        stopMotor();
        currentState = PAUSING;
        stateStartTime = currentMillis;
      }
      break;

    case PAUSING:
      stopMotor();
      // รอเฉยๆ ไม่ต้องทำอะไร
      if (currentMillis - stateStartTime >= PAUSE_TIME) {
        currentState = REVERSING;
        stateStartTime = currentMillis;
      }
      break;

    case REVERSING:
      // สั่งมอเตอร์ถอยหลัง
      analogWrite(RPWM_Output, 220); // *ปรับความเร็วตรงนี้*
      analogWrite(LPWM_Output, 0);

      // (ถ้าอยากเก็บกราฟขากลับด้วย ให้ใส่โค้ดส่ง DATA ตรงนี้)

      // เช็คเวลา
      if (currentMillis - stateStartTime >= RUN_TIMEOUT) {
        stopMotor();
        currentState = FINISHED; // จบการทำงาน
      }
      break;

    case FINISHED:
      stopMotor();
      Serial.println("STATUS:FINISHED"); // บอก Python ว่าจบแล้ว
      currentState = IDLE; // กลับไปรอรอบใหม่
      break;
  }
}

void stopMotor() {
  analogWrite(RPWM_Output, 0);
  analogWrite(LPWM_Output, 0);
}