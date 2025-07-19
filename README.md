# Edgehax Board Tester

Professional automated testing tool for Edgehax boards.

## Setup on Ubuntu/Windows
1. Install Python 3[](https://python.org).
2. Run: python3 -m venv env && source env/bin/activate (Linux) or .\env\Scripts\activate (Windows).
3. Run: pip install -r requirements.txt
4. Install arduino-cli (Ubuntu: curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh; Windows: download from https://arduino.github.io/arduino-cli/installation/).
5. Run: arduino-cli core install esp32:esp32
6. Place edgehax_test folder in ~ (Ubuntu) or Documents (Windows).
7. Run: python edgehax_board_tester.py

## Make Executable
pip install pyinstaller
pyinstaller --onefile --windowed edgehax_board_tester.py
