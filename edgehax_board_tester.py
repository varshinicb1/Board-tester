# Proprietary Software - Do not distribute or copy without permission from Varshini CB. All rights reserved. © 2025 Varshini CB

import sys
import os
import subprocess
import time
import json
import serial
import serial.tools.list_ports
import csv
import dearpygui.dearpygui as dpg

# Configuration
SKETCH_DIR = os.path.expanduser("~/edgehax_test") if sys.platform != 'win32' else os.path.join(os.environ['USERPROFILE'], 'edgehax_test')
BOARD_FQBN = "esp32:esp32:esp32-wroom-da"
ARDUINO_CLI = "arduino-cli"
POLL_INTERVAL = 1.0  # Seconds
VID_PID = (0x1A86, 0x7523)
BAUD_RATE = 115200
TIMEOUT = 60
LOGO_PATH = os.path.expanduser("~/Downloads/Edgehax-no-bg.png") if sys.platform != 'win32' else os.path.join(os.environ['USERPROFILE'], 'Downloads', 'Edgehax-no-bg.png')
CONFETTI_GIF = os.path.expanduser("~/Downloads/confetti.gif") if sys.platform != 'win32' else os.path.join(os.environ['USERPROFILE'], 'Downloads', 'confetti.gif')
CONFIG_FILE = os.path.expanduser("~/edgehax_tester/config.json")

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

# Initialize Dear PyGui context
try:
    dpg.create_context()
except Exception as e:
    print("Failed to create Dear PyGui context: " + str(e))
    sys.exit(1)

# Global variables
ser = None
board_port = None
test_results = []
known_ports = set()
try:
    known_ports = set([port.device for port in serial.tools.list_ports.comports()])
except Exception as e:
    print("Failed to initialize serial ports: " + str(e))
dark_theme = True
wifi_ssid = "YOUR_WIFI_SSID"
wifi_password = "YOUR_WIFI_PASSWORD"
sms_target = "9380763393"
progress = 0
voltage_x = []
voltage_y = []

# Load config
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            wifi_ssid = config.get('wifi_ssid', "YOUR_WIFI_SSID")
            wifi_password = config.get('wifi_password', "YOUR_WIFI_PASSWORD")
            sms_target = config.get('sms_target', "9380763393")
            dark_theme = config.get('dark_theme', True)
    except Exception as e:
        print("Failed to load config: " + str(e))

# Save config
def save_config():
    global wifi_ssid, wifi_password, sms_target, dark_theme
    config = {
        'wifi_ssid': wifi_ssid,
        'wifi_password': wifi_password,
        'sms_target': sms_target,
        'dark_theme': dark_theme
    }
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except Exception as e:
        print("Failed to save config: " + str(e))

# Theme functions
def set_dark_theme():
    try:
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (18, 18, 18, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (0, 255, 255, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (30, 30, 30, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (0, 255, 255, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (0, 200, 200, 255))
                # Use generic color for progress and plot to avoid version issues
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (0, 255, 255, 255))  # For progress bar
                dpg.add_theme_color(dpg.mvThemeCol_PlotLines, (0, 255, 255, 255))  # For plot
        dpg.bind_theme(global_theme)
    except Exception as e:
        print("Failed to apply dark theme: " + str(e))
        dpg.bind_theme(None)  # Fallback to default

def set_light_theme():
    try:
        with dpg.theme() as global_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (240, 240, 240, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (0, 0, 0, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (220, 220, 220, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (0, 0, 0, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (50, 50, 50, 255))
                # Use generic color for progress and plot to avoid version issues
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (0, 0, 0, 255))  # For progress bar
                dpg.add_theme_color(dpg.mvThemeCol_PlotLines, (0, 0, 0, 255))  # For plot
        dpg.bind_theme(global_theme)
    except Exception as e:
        print("Failed to apply light theme: " + str(e))
        dpg.bind_theme(None)  # Fallback to default

# Apply theme
if dark_theme:
    set_dark_theme()
else:
    set_light_theme()

# Guidelines modal
with dpg.window(label="Hardware Setup Guidelines", modal=True, show=False, tag="guidelines_modal", width=600, height=400):
    dpg.add_text("""
1. Insert 4G SIM (data/SMS plan) in drawer slot.
2. Insert SD card (up to 128GB) for logging.
3. Attach antennas (SMA for 4G/GNSS).
4. For voltage: Connect 10k/3.3k divider from 9V input to GPIO35 and GND.
5. Power with 9V 2A DC (NOT 12V!).
6. For UART loopback: Jumper TX2 (GPIO17) to RX2 (GPIO16).
7. For power: Use multimeter in series with 9V supply during tests (77mA working, 165mA peak expected).
8. Plug USB Type-C. Tests start automatically.
    """)
    dpg.add_button(label="Close", callback=lambda: dpg.configure_item("guidelines_modal", show=False))

# Error modals
with dpg.window(label="Detection Error", modal=True, show=False, tag="detection_error_modal", width=400, height=200):
    dpg.add_text("", tag="detection_error_text")
    dpg.add_button(label="Close", callback=lambda: dpg.configure_item("detection_error_modal", show=False))

with dpg.window(label="Upload Error", modal=True, show=False, tag="upload_error_modal", width=400, height=200):
    dpg.add_text("", tag="upload_error_text")
    dpg.add_button(label="Close", callback=lambda: dpg.configure_item("upload_error_modal", show=False))

with dpg.window(label="Connection Error", modal=True, show=False, tag="connection_error_modal", width=400, height=200):
    dpg.add_text("", tag="connection_error_text")
    dpg.add_button(label="Close", callback=lambda: dpg.configure_item("connection_error_modal", show=False))

with dpg.window(label="Test Error", modal=True, show=False, tag="test_error_modal", width=400, height=200):
    dpg.add_text("", tag="test_error_text")
    dpg.add_button(label="Close", callback=lambda: dpg.configure_item("test_error_modal", show=False))

with dpg.window(label="Settings Error", modal=True, show=False, tag="settings_error_modal", width=400, height=200):
    dpg.add_text("", tag="settings_error_text")
    dpg.add_button(label="Close", callback=lambda: dpg.configure_item("settings_error_modal", show=False))

# Main window
with dpg.window(tag="main_window", label="Edgehax Board Tester v1.0 - Created by Varshini CB", width=1000, height=800):
    # Logo
    try:
        dpg.add_image(LOGO_PATH, width=150, height=150, tag="logo_image")
    except Exception as e:
        dpg.add_text("Logo Not Found: " + str(e), tag="logo_image")

    # Branding
    dpg.add_text("Edgehax Board Tester", tag="branding_label")

    # Status
    dpg.add_text("Status: Waiting for Board Connection...", tag="status_label")

    # Progress
    dpg.add_progress_bar(tag="progress_bar", default_value=0.0, width=-1, overlay="0 / " + str(len(TESTS)) + " Tests Completed")

    # Table
    with dpg.table(header_row=True, borders_innerH=True, borders_outerH=True, borders_innerV=True, borders_outerV=True, tag="test_table"):
        dpg.add_table_column(label="Test")
        dpg.add_table_column(label="Status")
        dpg.add_table_column(label="Details")
        for test in TESTS:
            with dpg.table_row():
                dpg.add_text(test.replace("test_", "").upper().replace("_", " "), tag=test + "_test")
                dpg.add_text("Pending", tag=test + "_status")
                dpg.add_text("", tag=test + "_details")

    # Voltage plot
    with dpg.plot(label="Real-Time Voltage Monitor", height=300, width=-1, tag="voltage_plot", show=False):
        dpg.add_plot_legend()
        dpg.add_plot_axis(dpg.mvXAxis, label="Time (s)", tag="voltage_x_axis")
        with dpg.plot_axis(dpg.mvYAxis, label="Voltage (V)", tag="voltage_y_axis"):
            dpg.add_line_series(voltage_x, voltage_y, label="Voltage", tag="voltage_series")

    # Confetti
    try:
        dpg.add_image(CONFETTI_GIF, tag="confetti", show=False)
    except Exception as e:
        dpg.add_text("Confetti Not Found: " + str(e), tag="confetti", show=False)

    # Buttons
    dpg.add_button(label="Export Logs to CSV", callback=lambda: export_logs(None, None))
    dpg.add_button(label="Settings", callback=lambda: open_settings(None, None))
    dpg.add_button(label="Toggle Theme", callback=lambda: toggle_theme(None, None))
    dpg.add_button(label="Show Guidelines", callback=lambda: dpg.configure_item("guidelines_modal", show=True))

    # Footer
    dpg.add_text("Created by Varshini CB", tag="footer_label")

# Settings modal
with dpg.window(label="Settings", modal=True, show=False, tag="settings_modal", width=400, height=300):
    dpg.add_input_text(label="WiFi SSID", default_value=wifi_ssid, tag="wifi_ssid_input")
    dpg.add_input_text(label="WiFi Password", default_value=wifi_password, tag="wifi_password_input")
    dpg.add_input_text(label="SMS Target", default_value=sms_target, tag="sms_target_input")
    dpg.add_button(label="Save", callback=lambda: save_settings(None, None))
    dpg.add_button(label="Close", callback=lambda: dpg.configure_item("settings_modal", show=False))

def detect_board(sender, app_data):
    global known_ports, ser, board_port, test_results, progress, voltage_x, voltage_y
    try:
        current_ports = {port.device for port in serial.tools.list_ports.comports()}
        new_ports = current_ports - known_ports
        if new_ports:
            for port in serial.tools.list_ports.comports():
                if port.device in new_ports and (port.vid, port.pid) == VID_PID:
                    board_port = port.device
                    dpg.set_value("status_label", "Board detected on " + board_port + ". Uploading sketch...")
                    upload_sketch()
                    break
        known_ports = current_ports
    except Exception as e:
        dpg.set_value("status_label", "Detection error: " + str(e))
        dpg.set_value("detection_error_text", "Detection error: " + str(e) + "\\nReplug board or check drivers: https://wch-ic.com/downloads/CH341SER_ZIP.html")
        dpg.configure_item("detection_error_modal", show=True)

def upload_sketch():
    global ser, board_port
    try:
        subprocess.run([ARDUINO_CLI, "compile", "--fqbn", BOARD_FQBN, SKETCH_DIR], check=True, capture_output=True, text=True)
        subprocess.run([ARDUINO_CLI, "upload", "-p", board_port, "--fqbn", BOARD_FQBN, SKETCH_DIR], check=True, capture_output=True, text=True)
        time.sleep(2)
        connect_serial()
    except Exception as e:
        dpg.set_value("status_label", "Upload failed: " + str(e))
        dpg.set_value("upload_error_text", "Failed to upload sketch: " + str(e) + "\\nCheck arduino-cli, board power/USB, or drivers: https://arduino.github.io/arduino-cli/installation/")
        dpg.configure_item("upload_error_modal", show=True)

def connect_serial():
    global ser, board_port, test_results, progress
    try:
        ser = serial.Serial(board_port, BAUD_RATE, timeout=1)
        time.sleep(2)
        line = ser.readline().decode('utf-8').strip()
        if "ready" in line:
            dpg.set_value("status_label", "Connected to " + board_port + ". Starting automatic tests...")
            start_tests()
        else:
            raise Exception("No ready signal")
    except Exception as e:
        dpg.set_value("status_label", "Connection failed: " + str(e))
        dpg.set_value("connection_error_text", "Failed to connect: " + str(e) + "\\nReplug board or check drivers: https://wch-ic.com/downloads/CH341SER_ZIP.html")
        dpg.configure_item("connection_error_modal", show=True)

def start_tests():
    global ser, test_results, progress, voltage_x, voltage_y
    try:
        test_results = []
        progress = 0
        dpg.set_value("progress_bar", 0.0)
        dpg.configure_item("progress_bar", overlay="0 / " + str(len(TESTS)) + " Tests Completed")
        for test in TESTS:
            dpg.set_value(test + "_status", "Running...")
            result = run_single_test(test)
            status = "Pass" if result.get("success", False) else "Fail"
            details = result.get("details", "")
            if "wifi" in test and not result.get("success", False):
                details += " (Invalid credentials - Update in Settings)"
            elif "sim" in test and not result.get("success", False):
                details += " (Check SIM insertion/network)"
            elif "sd" in test and not result.get("success", False):
                details += " (Check SD card insertion)"
            dpg.set_value(test + "_status", status)
            dpg.set_value(test + "_details", details)
            test_results.append({"Test": test.replace("test_", "").upper().replace("_", " "), "Status": status, "Details": details})
            progress += 1
            dpg.set_value("progress_bar", progress / len(TESTS))
            dpg.configure_item("progress_bar", overlay=str(progress) + " / " + str(len(TESTS)) + " Tests Completed")
            if test == "test_voltage":
                update_voltage_plot()
        dpg.set_value("status_label", "Testing Complete. Results logged to SD card. Unplug and replug for next board.")
        if all(r['Status'] == "Pass" for r in test_results):
            dpg.configure_item("confetti", show=True)
            time.sleep(5)
            dpg.configure_item("confetti", show=False)
    except Exception as e:
        dpg.set_value("status_label", "Test error: " + str(e))
        dpg.set_value("test_error_text", "Testing interrupted: " + str(e) + "\\nReplug and try again.")
        dpg.configure_item("test_error_modal", show=True)

def run_single_test(test_name):
    global ser, voltage_x, voltage_y
    try:
        ser.write((test_name + "\n").encode())
        start_time = time.time()
        voltage_y = []
        voltage_x = []
        while time.time() - start_time < TIMEOUT:
            line = ser.readline().decode('utf-8').strip()
            if line:
                try:
                    data = json.loads(line)
                    if test_name == "test_voltage":
                        voltage_y.append(float(data.get("voltage", 0)))
                        voltage_x.append(len(voltage_y) - 1)
                    return data
                except json.JSONDecodeError:
                    continue
        return {"success": False, "details": "Timeout - Check connections/antennas."}
    except Exception as e:
        return {"success": False, "details": "Error: " + str(e) + " - Replug board."}

def update_voltage_plot():
    global voltage_x, voltage_y
    try:
        if voltage_x and voltage_y:
            dpg.set_value("voltage_series", [voltage_x, voltage_y])
            dpg.configure_item("voltage_plot", show=True)
    except Exception as e:
        dpg.set_value("status_label", "Voltage plot update failed: " + str(e))

def open_settings(sender, app_data):
    global wifi_ssid, wifi_password, sms_target
    dpg.configure_item("settings_modal", show=True)

def save_settings(sender, app_data):
    global wifi_ssid, wifi_password, sms_target, ser
    try:
        wifi_ssid = dpg.get_value("wifi_ssid_input")
        wifi_password = dpg.get_value("wifi_password_input")
        sms_target = dpg.get_value("sms_target_input")
        save_config()
        dpg.configure_item("settings_modal", show=False)
        if ser:
            ser.write(("set_wifi:" + wifi_ssid + ":" + wifi_password + "\\n").encode())
            line = ser.readline().decode('utf-8').strip()
            if "wifi_updated" not in line:
                raise Exception("WiFi update failed")
            ser.write(("set_sms:" + sms_target + "\\n").encode())
            line = ser.readline().decode('utf-8').strip()
            if "sms_updated" not in line:
                raise Exception("SMS update failed")
            dpg.set_value("status_label", "Settings updated successfully.")
    except Exception as e:
        dpg.set_value("status_label", "Settings update failed: " + str(e))
        dpg.set_value("settings_error_text", "Settings update failed: " + str(e) + "\\nCheck board connection.")
        dpg.configure_item("settings_error_modal", show=True)

def toggle_theme(sender, app_data):
    global dark_theme
    try:
        dark_theme = not dark_theme
        if dark_theme:
            set_dark_theme()
        else:
            set_light_theme()
        save_config()
        dpg.set_value("status_label", "Theme switched successfully.")
    except Exception as e:
        dpg.set_value("status_label", "Theme switch failed: " + str(e))

def export_logs(sender, app_data):
    global test_results
    try:
        with dpg.file_dialog(directory_selector=False, default_extension=".csv", callback=export_logs_callback, modal=True):
            dpg.add_file_extension(".csv")
    except Exception as e:
        dpg.set_value("status_label", "Failed to open file dialog: " + str(e))

def export_logs_callback(sender, app_data):
    global test_results
    try:
        file_path = app_data['file_path_name']
        with open(file_path, 'w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=["Test", "Status", "Details"])
            writer.writeheader()
            writer.writerows(test_results)
        dpg.set_value("status_label", "Logs exported successfully to " + file_path)
    except Exception as e:
        dpg.set_value("status_label", "Failed to export logs: " + str(e))

if __name__ == "__main__":
    try:
        dpg.create_viewport(title="Edgehax Board Tester", width=1000, height=800)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("main_window", True)
        dpg.set_render_callback(detect_board)
        dpg.configure_item("guidelines_modal", show=True)
        dpg.start_dearpygui()
    except Exception as e:
        print("Application failed to start: " + str(e))
    finally:
        if ser:
            try:
                ser.close()
            except:
                pass
        dpg.destroy_context()
