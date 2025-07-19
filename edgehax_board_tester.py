import sys
import os
import subprocess
import time
import json
import serial
import serial.tools.list_ports
import csv
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QProgressBar, QGraphicsDropShadowEffect, QFileDialog, QToolTip, QMessageBox, QInputDialog
from PyQt5.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve, QSettings
from PyQt5.QtGui import QColor, QFont, QPixmap, QMovie, QIcon
try:
    from pyqtgraph import PlotWidget, mkPen
except ImportError:
    QMessageBox.critical(None, "Missing Package", "Please run: pip install pyqtgraph")
    sys.exit(1)

# Configuration
SKETCH_DIR = os.path.expanduser("~/edgehax_test") if sys.platform != 'win32' else os.path.join(os.environ['USERPROFILE'], 'edgehax_test')
BOARD_FQBN = "esp32:esp32:esp32-wroom-da"
ARDUINO_CLI = "arduino-cli"
POLL_INTERVAL = 1000
VID_PID = (0x1A86, 0x7523)
BAUD_RATE = 115200
TIMEOUT = 60
LOGO_PATH = os.path.expanduser("~/Downloads/Edgehax-no-bg.png") if sys.platform != 'win32' else os.path.join(os.environ['USERPROFILE'], 'Downloads', 'Edgehax-no-bg.png')
CONFETTI_GIF = os.path.expanduser("~/Downloads/confetti.gif") if sys.platform != 'win32' else os.path.join(os.environ['USERPROFILE'], 'Downloads', 'confetti.gif')
CONFIG_ORG = "VarshiniCB"
CONFIG_APP = "EdgehaxTester"

TESTS = [
    "test_led",
    "test_leds",
    "test_wifi",
    "test_wifi_http",
    "test_4g_at",
    "test_4g_sim",
    "test_4g_network",
    "test_at_commands",
    "test_sd_card",
    "test_navic",
    "test_voltage",
    "test_peripherals"
]

class EdgehaxTester(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Edgehax Board Tester v1.0 - Created by Varshini CB")
        self.setGeometry(100, 100, 1000, 800)
        
        self.settings = QSettings(CONFIG_ORG, CONFIG_APP)
        self.dark_theme = self.settings.value('dark_theme', True, type=bool)
        self.wifi_ssid = self.settings.value('wifi_ssid', "YOUR_WIFI_SSID")
        self.wifi_password = self.settings.value('wifi_password', "YOUR_WIFI_PASSWORD")
        self.sms_target = self.settings.value('sms_target', "9380763393")
        self.apply_theme()
        
        try:
            subprocess.run([ARDUINO_CLI, "version"], capture_output=True, check=True)
        except:
            QMessageBox.critical(self, "Setup Error", "Install arduino-cli:\\nUbuntu: curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh\\nWindows: Download from https://arduino.github.io/arduino-cli/installation/\\nThen run: arduino-cli core install esp32:esp32")
        
        # Guidelines
        guidelines = """
1. Insert 4G SIM (data/SMS plan) in drawer slot.
2. Insert SD card (up to 128GB) for logging.
3. Attach antennas (SMA for 4G/GNSS).
4. For voltage: Connect 10k/3.3k divider from 9V input to GPIO35 and GND.
5. Power with 9V 2A DC (NOT 12V!).
6. For UART loopback: Jumper TX2 (GPIO17) to RX2 (GPIO16).
7. For power: Use multimeter in series with 9V supply during tests (77mA working, 165mA peak expected).
8. Plug USB Type-C. Tests start automatically.
        """
        QMessageBox.information(self, "Hardware Setup Guidelines", guidelines)
        
        # Logo
        logo_label = QLabel()
        pixmap = QPixmap(LOGO_PATH)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(pixmap)
        else:
            logo_label.setText("Logo Not Found")
        logo_label.setAlignment(Qt.AlignCenter)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 255, 255, 128) if self.dark_theme else QColor(0, 0, 0, 128))
        shadow.setOffset(0, 0)
        logo_label.setGraphicsEffect(shadow)
        
        # Branding
        branding_label = QLabel("Edgehax Board Tester")
        branding_label.setFont(QFont("Arial", 20, QFont.Bold))
        branding_label.setAlignment(Qt.AlignCenter)
        
        # Status
        self.status_label = QLabel("Status: Waiting for Board Connection...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setToolTip("Plug in the Edgehax board to start automatic testing.")
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(len(TESTS))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%v / %m Tests Completed")
        self.progress_bar.setToolTip("Test progress - Automatic, no action needed.")
        
        # Table
        self.table = QTableWidget()
        self.table.setRowCount(len(TESTS))
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Test", "Status", "Details"])
        self.table.setAlternatingRowColors(True)
        for row, test in enumerate(TESTS):
            item_test = QTableWidgetItem(test.replace("test_", "").upper().replace("_", " "))
            item_test.setToolTip("Automatic test for " + test.replace("test_", "").upper())
            self.table.setItem(row, 0, item_test)
            self.table.setItem(row, 1, QTableWidgetItem("Pending"))
            self.table.setItem(row, 2, QTableWidgetItem(""))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setToolTip("Results - Green: Pass, Red: Fail. Logs to SD card.")
        
        # Voltage graph
        try:
            self.voltage_graph = PlotWidget()
            self.voltage_graph.setTitle("Real-Time Voltage Monitor")
            self.voltage_graph.setLabel('left', 'Voltage (V)')
            self.voltage_graph.setLabel('bottom', 'Time (s)')
            self.voltage_graph.hide()
            self.voltage_data = []
            self.voltage_plot = self.voltage_graph.plot(pen=mkPen('c', width=2))
        except Exception as e:
            self.status_label.setText("Voltage graph init failed: " + str(e))
            self.voltage_graph = None
        
        # Confetti
        self.confetti_label = QLabel()
        try:
            self.confetti_movie = QMovie(CONFETTI_GIF)
            self.confetti_label.setMovie(self.confetti_movie)
            self.confetti_label.hide()
        except Exception as e:
            self.status_label.setText("Confetti animation init failed: " + str(e))
        
        # Export
        export_btn = QPushButton("Export Logs to CSV")
        export_btn.clicked.connect(self.export_logs)
        export_btn.setToolTip("Save results to CSV on your computer.")
        
        # Settings
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings)
        settings_btn.setToolTip("Change WiFi, SMS, theme, etc.")
        
        # Theme toggle
        theme_btn = QPushButton("Switch to Light Theme" if self.dark_theme else "Switch to Dark Theme")
        theme_btn.clicked.connect(self.toggle_theme)
        
        # Footer
        footer_label = QLabel("Created by Varshini CB")
        footer_label.setFont(QFont("Arial", 10))
        footer_label.setAlignment(Qt.AlignCenter)
        
        # Layout
        layout = QVBoxLayout()
        layout.addWidget(logo_label)
        layout.addWidget(branding_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.table)
        if self.voltage_graph:
            layout.addWidget(self.voltage_graph)
        layout.addWidget(self.confetti_label)
        layout.addWidget(export_btn)
        layout.addWidget(settings_btn)
        layout.addWidget(theme_btn)
        layout.addWidget(footer_label)
        
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        
        # Detection
        self.known_ports = set(self.get_current_ports())
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.detect_board)
        self.timer.start(POLL_INTERVAL)
        
        self.ser = None
        self.board_port = None
        self.test_results = []

    def apply_theme(self):
        if self.dark_theme:
            self.setStyleSheet("""
                QMainWindow {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #121212, stop:1 #1E1E1E);
                    color: #00FFFF;
                }
                QLabel {
                    color: #00FFFF;
                }
                QPushButton {
                    background-color: #1E1E1E;
                    color: #00FFFF;
                    border: 2px solid #00FFFF;
                }
                QPushButton:hover {
                    background-color: #00FFFF;
                    color: #121212;
                }
                QTableWidget {
                    background-color: #1E1E1E;
                    color: #FFFFFF;
                    gridline-color: #00FFFF;
                    alternate-background-color: #2A2A2A;
                }
                QProgressBar {
                    background-color: #1E1E1E;
                    border: 2px solid #00FFFF;
                    color: #00FFFF;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00FFFF, stop:1 #008080);
                }
            """)
            if self.voltage_graph:
                self.voltage_graph.setBackground('#1E1E1E')
                self.voltage_graph.getAxis('left').setTextPen('#00FFFF')
                self.voltage_graph.getAxis('bottom').setTextPen('#00FFFF')
                self.voltage_graph.setTitle("Real-Time Voltage Monitor", color="#00FFFF")
        else:
            self.setStyleSheet("""
                QMainWindow {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #F0F0F0);
                    color: #000000;
                }
                QLabel {
                    color: #000000;
                }
                QPushButton {
                    background-color: #F0F0F0;
                    color: #000000;
                    border: 2px solid #000000;
                }
                QPushButton:hover {
                    background-color: #000000;
                    color: #FFFFFF;
                }
                QTableWidget {
                    background-color: #FFFFFF;
                    color: #000000;
                    gridline-color: #CCCCCC;
                    alternate-background-color: #F0F0F0;
                }
                QProgressBar {
                    background-color: #F0F0F0;
                    border: 2px solid #000000;
                    color: #000000;
                }
                QProgressBar::chunk {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #CCCCCC, stop:1 #AAAAAA);
                }
            """)
            if self.voltage_graph:
                self.voltage_graph.setBackground('#FFFFFF')
                self.voltage_graph.getAxis('left').setTextPen('#000000')
                self.voltage_graph.getAxis('bottom').setTextPen('#000000')
                self.voltage_graph.setTitle("Real-Time Voltage Monitor", color="#000000")

    def toggle_theme(self):
        self.dark_theme = not self.dark_theme
        self.apply_theme()
        self.settings.setValue('dark_theme', self.dark_theme)
        self.settings.sync()

    def open_settings(self):
        ssid, ok = QInputDialog.getText(self, "WiFi Settings", "Enter WiFi SSID:", text=self.wifi_ssid)
        if ok:
            self.wifi_ssid = ssid
            password, ok = QInputDialog.getText(self, "WiFi Settings", "Enter WiFi Password:", text=self.wifi_password)
            if ok:
                self.wifi_password = password
                if self.ser:
                    try:
                        self.ser.write(("set_wifi:" + ssid + ":" + password + "\\n").encode())
                        line = self.ser.readline().decode('utf-8').strip()
                        if "wifi_updated" in line:
                            QMessageBox.information(self, "Success", "WiFi updated on board.")
                        else:
                            raise Exception("Update failed")
                    except Exception as e:
                        QMessageBox.warning(self, "Error", "Failed to update WiFi on board: " + str(e) + "\\nCheck board connection.")
        sms, ok = QInputDialog.getText(self, "SMS Settings", "Enter SMS Target Phone:", text=self.sms_target)
        if ok:
            self.sms_target = sms
            if self.ser:
                try:
                    self.ser.write(("set_sms:" + sms + "\\n").encode())
                    line = self.ser.readline().decode('utf-8').strip()
                    if "sms_updated" in line:
                        QMessageBox.information(self, "Success", "SMS target updated on board.")
                    else:
                        raise Exception("Update failed")
                except Exception as e:
                    QMessageBox.warning(self, "Error", "Failed to update SMS on board: " + str(e) + "\\nCheck board connection.")
        self.settings.setValue('wifi_ssid', self.wifi_ssid)
        self.settings.setValue('wifi_password', self.wifi_password)
        self.settings.setValue('sms_target', self.sms_target)
        self.settings.sync()

    def get_current_ports(self):
        try:
            return {port.device for port in serial.tools.list_ports.comports()}
        except Exception as e:
            QMessageBox.warning(self, "Error", "Serial ports scan failed: " + str(e) + "\\nInstall drivers or check USB.")
            return set()

    def detect_board(self):
        try:
            current_ports = self.get_current_ports()
            new_ports = current_ports - self.known_ports
            if new_ports:
                for port in serial.tools.list_ports.comports():
                    if port.device in new_ports and (port.vid, port.pid) == VID_PID:
                        self.board_port = port.device
                        self.status_label.setText("Board detected on " + self.board_port + ". Uploading sketch...")
                        self.animate_fade(self.status_label)
                        self.upload_sketch()
                        break
            self.known_ports = current_ports
        except Exception as e:
            self.status_label.setText("Detection error: " + str(e))

    def upload_sketch(self):
        try:
            cmd = [ARDUINO_CLI, "compile", "--fqbn", BOARD_FQBN, SKETCH_DIR]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            cmd = [ARDUINO_CLI, "upload", "-p", self.board_port, "--fqbn", BOARD_FQBN, SKETCH_DIR]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            time.sleep(2)
            self.connect_serial()
        except Exception as e:
            self.status_label.setText("Upload failed: " + str(e))
            QMessageBox.critical(self, "Upload Error", "Failed to upload sketch: " + str(e) + "\\nCheck arduino-cli, board power/USB, or drivers.")

    def connect_serial(self):
        try:
            self.ser = serial.Serial(self.board_port, BAUD_RATE, timeout=1)
            time.sleep(2)
            line = self.ser.readline().decode('utf-8').strip()
            if "ready" in line:
                self.status_label.setText("Connected to " + self.board_port + ". Starting automatic tests...")
                self.animate_fade(self.status_label)
                self.start_tests()
            else:
                raise Exception("No ready signal")
        except Exception as e:
            self.status_label.setText("Connection failed: " + str(e))
            QMessageBox.warning(self, "Connection Error", "Failed to connect: " + str(e) + "\\nReplug board or check drivers.")

    def start_tests(self):
        try:
            self.status_label.setText("Testing in progress... Please wait (automatic).")
            self.progress_bar.setValue(0)
            self.test_results = []
            for row, test in enumerate(TESTS):
                self.table.item(row, 1).setText("Running...")
                self.table.item(row, 1).setBackground(QColor(255, 255, 0))
                QApplication.processEvents()
                
                result = self.run_single_test(test)
                status = "Pass" if result.get("success", False) else "Fail"
                details = result.get("details", "")
                if "wifi" in test and not result.get("success", False):
                    details += " (Invalid credentials - Update in Settings)"
                elif "sim" in test and not result.get("success", False):
                    details += " (Check SIM insertion/network)"
                elif "sd" in test and not result.get("success", False):
                    details += " (Check SD card insertion)"
                
                self.table.item(row, 1).setText(status)
                self.table.item(row, 1).setBackground(QColor(0, 255, 0) if result.get("success", False) else QColor(255, 0, 0))
                self.table.item(row, 2).setText(details)
                self.progress_bar.setValue(row + 1)
                self.animate_fade(self.table.item(row, 1))
                self.test_results.append({"Test": test.replace("test_", "").upper().replace("_", " "), "Status": status, "Details": details})
                QApplication.processEvents()
            
            self.status_label.setText("Testing Complete. Results logged to SD card. Unplug and replug for next board.")
            self.animate_fade(self.status_label)
            if all(r['Status'] == "Pass" for r in self.test_results):
                self.confetti_label.show()
                self.confetti_movie.start()
                time.sleep(5)
                self.confetti_movie.stop()
                self.confetti_label.hide()
        except Exception as e:
            self.status_label.setText("Test error: " + str(e))
            QMessageBox.warning(self, "Test Error", "Testing interrupted: " + str(e) + "\\nReplug and try again.")

    def run_single_test(self, test_name):
        try:
            self.ser.write((test_name + "\n").encode())
            start_time = time.time()
            while time.time() - start_time < TIMEOUT:
                line = self.ser.readline().decode('utf-8').strip()
                if line:
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        continue
            return {"success": False, "details": "Timeout - Check connections/antennas."}
        except Exception as e:
            return {"success": False, "details": "Error: " + str(e) + " - Replug board."}
        finally:
            if test_name == "test_voltage" and self.voltage_graph:
                self.voltage_graph.show()
                self.voltage_data = []
                for _ in range(20):
                    try:
                        self.ser.write((test_name + "\n").encode())
                        line = self.ser.readline().decode('utf-8').strip()
                        if line:
                            data = json.loads(line)
                            v = data.get("voltage", 0)
                            self.voltage_data.append(v)
                            self.voltage_plot.setData(self.voltage_data)
                            QApplication.processEvents()
                    except:
                        pass
                    time.sleep(0.5)
                self.voltage_graph.hide()
                if self.voltage_data:
                    avg_v = sum(self.voltage_data) / len(self.voltage_data)
                else:
                    avg_v = 0
                return {"success": (7 < avg_v < 9), "details": "Average: " + str(round(avg_v, 2)) + "V"}

    def animate_fade(self, widget):
        try:
            animation = QPropertyAnimation(widget, b"windowOpacity")
            animation.setDuration(500)
            animation.setStartValue(0.5)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.InOutQuad)
            animation.start()
        except Exception as e:
            pass  # Animation optional

    def export_logs(self):
        try:
            file_path, _ = QFileDialog.getSaveFileName(self, "Save Logs", "", "CSV Files (*.csv)")
            if file_path:
                with open(file_path, 'w', newline='') as file:
                    writer = csv.DictWriter(file, fieldnames=["Test", "Status", "Details"])
                    writer.writeheader()
                    writer.writerows(self.test_results)
                self.status_label.setText("Logs exported successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Export Error", "Failed to export: " + str(e))

    def closeEvent(self, event):
        if self.ser:
            try:
                self.ser.close()
            except:
                pass
        event.accept()

if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = EdgehaxTester()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        QMessageBox.critical(None, "Startup Error", "Application failed to start: " + str(e) + "\\nCheck Python installation and dependencies.")
