#include <WiFi.h>
#include <HTTPClient.h>
#include <SD.h>
#include <TinyGPS++.h>
#include <SoftwareSerial.h>
#include <ArduinoJson.h>
#include <time.h>
#include <Wire.h>

#define LED_PIN 2
#define SD_CS_PIN 5
#define MODEM_RX 16
#define MODEM_TX 17
#define VOLTAGE_PIN 35
#define GPIO_TEST_PIN 4
#define UART_LOOPBACK_TX 17
#define UART_LOOPBACK_RX 16

String wifi_ssid = "YOUR_WIFI_SSID";
String wifi_password = "YOUR_WIFI_PASSWORD";
const char* test_server = "http://httpbin.org/get";
const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = 19800;
const int daylightOffset_sec = 0;
const char apn[] = "airtelgprs.com";
const char gprsUser[] = "";
const char gprsPass[] = "";
String send_data_to_url = "https://eogas6eaag50nu2.m.pipedream.net";
String sms_target = "9380763393";
const char* logFile = "/edgehax_log.txt";
const float voltageDividerRatio = 4.03;

SoftwareSerial modemSerial(MODEM_RX, MODEM_TX);
TinyGPSPlus gps;
StaticJsonDocument<1024> doc;

void setup() {
  Serial.begin(115200);
  modemSerial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(GPIO_TEST_PIN, OUTPUT);
  Wire.begin();
  initSD();
  Serial.println("{\"status\": \"ready\"}");
}

void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    if (command.startsWith("set_wifi:")) {
      int colon1 = command.indexOf(':', 9);
      wifi_ssid = command.substring(9, colon1);
      wifi_password = command.substring(colon1 + 1);
      Serial.println("{\"wifi_updated\": true}");
      return;
    } else if (command.startsWith("set_sms:")) {
      sms_target = command.substring(8);
      Serial.println("{\"sms_updated\": true}");
      return;
    }
    runTest(command);
  }
}

void initSD() {
  if (!SD.begin(SD_CS_PIN)) {
    logToSD("SD Init Failed");
    return;
  }
  logToSD("SD Init Success");
}

void logToSD(String message) {
  File file = SD.open(logFile, FILE_APPEND);
  if (file) {
    struct tm timeinfo;
    if (getLocalTime(&timeinfo)) {
      char timeStr[20];
      strftime(timeStr, sizeof(timeStr), "%d/%m/%Y %H:%M:%S", &timeinfo);
      file.print(timeStr);
      file.print(" - ");
    }
    file.println(message);
    file.close();
  }
}

bool getLocalTime(struct tm * info) {
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  return getLocalTime(info);
}

void runTest(String testName) {
  doc.clear();
  doc["test"] = testName;
  bool success = false;
  String details = "";

  if (testName == "test_led") {
    digitalWrite(LED_PIN, HIGH);
    delay(500);
    digitalWrite(LED_PIN, LOW);
    success = true;
    details = "LED blink success";
  } else if (testName == "test_wifi") {
    WiFi.begin(wifi_ssid.c_str(), wifi_password.c_str());
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 10) {
      delay(1000);
      attempts++;
    }
    success = WiFi.status() == WL_CONNECTED;
    if (success) {
      struct tm timeinfo;
      success = getLocalTime(&timeinfo);
      details = success ? "WiFi + Time Sync success" : "Time Sync failed";
    } else {
      details = "WiFi connect failed - Check credentials";
    }
    WiFi.disconnect();
  } else if (testName == "test_wifi_http") {
    if (WiFi.status() != WL_CONNECTED) WiFi.begin(wifi_ssid.c_str(), wifi_password.c_str());
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 10) {
      delay(1000);
      attempts++;
    }
    if (WiFi.status() == WL_CONNECTED) {
      HTTPClient http;
      http.begin(test_server);
      int httpCode = http.GET();
      success = httpCode > 0;
      details = success ? "HTTP GET success, code: " + String(httpCode) : "HTTP failed";
      http.end();
    } else {
      details = "WiFi not connected";
    }
    WiFi.disconnect();
  } else if (testName == "test_4g_at") {
    modemSerial.println("AT");
    details = readModemResponse(2000);
    success = details.indexOf("OK") >= 0;
  } else if (testName == "test_4g_sim") {
    modemSerial.println("AT+CPIN?");
    details = readModemResponse(2000);
    success = details.indexOf("+CPIN: READY") >= 0;
    if (success) {
      modemSerial.println("AT+CMGF=1");
      delay(500);
      modemSerial.println("AT+CMGS=\\"" + sms_target + "\\"");
      delay(500);
      modemSerial.print("Test SMS from Edgehax");
      modemSerial.write(26);
      details += readModemResponse(5000);
      success = details.indexOf("+CMGS") >= 0;
    }
  } else if (testName == "test_4g_network") {
    modemSerial.println("AT+CREG?");
    details = readModemResponse(2000);
    success = details.indexOf("+CREG: 0,1") >= 0 || details.indexOf("+CREG: 0,5") >= 0;
    if (success) {
      modemSerial.println("AT+HTTPINIT");
      delay(500);
      modemSerial.println("AT+HTTPPARA=\\"URL\\",\\"" + send_data_to_url + "\\"");
      delay(500);
      modemSerial.println("AT+HTTPPARA=\\"CONTENT\\",\\"text/plain\\"");
      delay(500);
      modemSerial.println("AT+HTTPDATA=20,10000");
      delay(500);
      modemSerial.println("Test from Edgehax");
      delay(500);
      modemSerial.println("AT+HTTPACTION=1");
      details += readModemResponse(5000);
      success = details.indexOf("+HTTPACTION: 1,200") >= 0;
      modemSerial.println("AT+HTTPTERM");
    }
  } else if (testName == "test_sd_card") {
    if (SD.begin(SD_CS_PIN)) {
      File testFile = SD.open("/test.txt", FILE_WRITE);
      if (testFile) {
        testFile.println("Test");
        testFile.close();
        success = SD.exists("/test.txt");
        SD.remove("/test.txt");
      }
      SD.end();
    }
    details = success ? "SD R/W success" : "SD failed";
  } else if (testName == "test_navic") {
    bool gps_data = false;
    unsigned long start = millis();
    while (millis() - start < 30000) {
      while (modemSerial.available()) {
        if (gps.encode(modemSerial.read())) {
          if (gps.location.isValid()) {
            gps_data = true;
            break;
          }
        }
      }
      if (gps_data) break;
    }
    if (gps_data) {
      doc["lat"] = gps.location.lat();
      doc["lng"] = gps.location.lng();
      doc["speed"] = gps.speed.knots();
      doc["course"] = gps.course.deg();
      doc["altitude"] = gps.altitude.meters();
      doc["satellites"] = gps.satellites.value();
      doc["hdop"] = gps.hdop.hdop();
      doc["date"] = gps.date.value();
      doc["time"] = gps.time.value();
      doc["maps_link"] = "http://maps.google.com/maps?q=" + String(gps.location.lat(), 6) + "," + String(gps.location.lng(), 6);
      success = true;
      details = "NavIC full params success";
    } else {
      details = "NavIC latch failed - Check antenna/sky";
    }
  } else if (testName == "test_voltage") {
    float voltage = 0;
    for (int i = 0; i < 10; i++) {
      int adc = analogRead(VOLTAGE_PIN);
      float v = (adc * 3.3 / 4095) * voltageDividerRatio;
      voltage += v;
      Serial.print("{\"voltage\":");
      Serial.print(v, 2);
      Serial.println("}");
      delay(500);
    }
    voltage /= 10;
    success = (voltage > 7 && voltage < 9);
    details = "Average voltage: " + String(voltage, 2) + "V";
  } else if (testName == "test_at_commands") {
    String atCommands[] = {"AT", "ATI", "AT+CPIN?", "AT+CREG?", "AT+CGATT?", "AT+CSCA?", "AT+HTTPINIT", "AT+CGNSSPWR=1"};
    int numCommands = sizeof(atCommands) / sizeof(atCommands[0]);
    success = true;
    details = "";
    for (int i = 0; i < numCommands; i++) {
      modemSerial.println(atCommands[i]);
      String resp = readModemResponse(2000);
      if (resp.indexOf("OK") < 0) success = false;
      details += atCommands[i] + ": " + resp + "; ";
    }
  } else if (testName == "test_peripherals") {
    Wire.begin();
    String i2cDetails = "I2C devices: ";
    for (byte address = 1; address < 127; address++) {
      Wire.beginTransmission(address);
      if (Wire.endTransmission() == 0) i2cDetails += String(address, HEX) + " ";
    }
    modemSerial.println("TEST");
    String uartResp = readModemResponse(1000);
    bool uartSuccess = uartResp.indexOf("TEST") >= 0;
    pinMode(GPIO_TEST_PIN, OUTPUT);
    digitalWrite(GPIO_TEST_PIN, HIGH);
    delay(100);
    pinMode(GPIO_TEST_PIN, INPUT);
    bool gpioSuccess = digitalRead(GPIO_TEST_PIN) == HIGH;
    success = (i2cDetails.length() > 12 && uartSuccess && gpioSuccess);
    details = i2cDetails + " UART loopback: " + (uartSuccess ? "Pass" : "Fail - Check jumper") + " GPIO: " + (gpioSuccess ? "Pass" : "Fail");
  } else if (testName == "test_leds") {
    digitalWrite(LED_PIN, HIGH);
    delay(500);
    digitalWrite(LED_PIN, LOW);
    modemSerial.println("AT");
    String modemResp = readModemResponse(2000);
    bool modemLed = modemResp.indexOf("OK") >= 0;
    modemSerial.println("AT+CREG?");
    String netResp = readModemResponse(2000);
    bool netLed = netResp.indexOf("+CREG: 0,1") >= 0;
    success = (true && modemLed && netLed);
    details = "POWER: On, MODEM: " + (modemLed ? "On" : "Off") + ", NETWORK: " + (netLed ? "On" : "Off") + ", CUSTOM: Toggled";
  } else {
    details = "Unknown test";
  }

  doc["success"] = success;
  doc["details"] = details;
  serializeJson(doc, Serial);
  Serial.println();
  logToSD(testName + ": " + (success ? "Pass" : "Fail") + " - " + details);
}

String readModemResponse(unsigned long timeout) {
  String response = "";
  unsigned long start = millis();
  while (millis() - start < timeout) {
    while (modemSerial.available()) {
      response += (char)modemSerial.read();
    }
  }
  return response;
}
