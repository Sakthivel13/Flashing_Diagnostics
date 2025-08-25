# -*- coding: utf-8 -*-
"""
Created on Mon Aug 11 12:35:12 2025

@author: A.Harshitha
"""

import io
import sys
import os
import configparser
import socket
import threading
import time
import requests
from PyQt5.QtWidgets import (
    QApplication, QAbstractItemView, QTextEdit, QWidget, QLabel, QHBoxLayout, QVBoxLayout, 
    QProgressBar, QFrame, QLineEdit, QComboBox, QPushButton, QButtonGroup, QSizePolicy, 
    QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView, QDialog
)
from PyQt5.QtGui import QFont, QColor, QPalette, QIntValidator,  QPixmap, QPainter, QLinearGradient, QIcon
from PyQt5.QtCore import Qt, QTimer, QObject, pyqtSignal, QThread
import serial.tools.list_ports
import importlib
import importlib.util
import pandas as pd
from datetime import datetime
import json
import serial
import usb.core
import usb.util
from contextlib import redirect_stdout, redirect_stderr

class TestWorker(QObject):
    result_ready = pyqtSignal(object, float, str)
    error_occurred = pyqtSignal(Exception, float, str)

    def __init__(self, library_name, function_name, vin_number, api_url, log_callback):
        super().__init__()
        self.library_name = library_name
        self.function_name = function_name
        self.vin_number = vin_number
        self.api_url = api_url
        self.log_callback = log_callback

    def run(self):
        import time, sys, importlib
        from contextlib import redirect_stdout, redirect_stderr

        stream = EmittingStream(self.log_callback)
        start_time = time.time()

        try:
            with redirect_stdout(stream), redirect_stderr(stream):
    
                # Special case: Flashing flow
                if self.function_name.lower() == "flashing":
                    # Call your existing flashing dialog process
                    self.run_flashing_process()
                    result = self.result  # Set in _handle_flashing_result
                else:
                    # Normal dynamic import flow
                    module_name = f"{self.library_name}.{self.function_name}"
    
                    if module_name in sys.modules:
                        importlib.reload(sys.modules[module_name])
                    else:
                        importlib.import_module(module_name)
    
                    test_function = getattr(sys.modules[module_name], self.function_name)
    
                    # Decide how to call the function
                    if self.library_name == "TPMS" or self.function_name in [
                        "MCU_Phase_Offset", "MCU_Vehicle_ID", "API_CALL"
                    ]:
                        result = test_function(self.vin_number, self.api_url)
                    else:
                        result = test_function()
    
        except Exception as e:
            duration = time.time() - start_time
            self.error_occurred.emit(e, duration, stream.get_logs())
            return
    
        duration = time.time() - start_time
        self.result_ready.emit(result, duration, stream.get_logs())
    
# To access files after converting to an exe/elf/runtime
def resource_path(relative_path):
    """ Get absolute path to resource (for bundled executable) """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

#Mapping corresponding sku based test sequence file
def get_file_name_from_sku(sku_number, active_library):
    mapping_file_path = resource_path(r"D:\TVS NIRIX Flashing\SKU_File_Mapping.xlsx")
    default_sku = "GE190510"
    try:
        df = pd.read_excel(mapping_file_path)
        df.columns = df.columns.str.strip()
        df["SKU No"] = df["SKU No"].astype(str).str.strip()
        df["File Name"] = df["File Name"].astype(str).str.strip()
        df["Library"] = df["Library"].astype(str).str.strip()
        lookup_sku = sku_number.strip() if sku_number else default_sku
        matched_row = df[(df["SKU No"] == lookup_sku) & (df["Library"] == active_library)]
        if not matched_row.empty:
            return matched_row.iloc[0]["File Name"], matched_row.iloc[0]["Library"]
        else:
            #print(f"SKU '{lookup_sku}' not found for library '{active_library}'. Checking for any library match.")
            matched_row = df[df["SKU No"] == lookup_sku]
            if not matched_row.empty:
                return None, matched_row.iloc[0]["Library"]
            #print(f"SKU '{lookup_sku}' not found in any library. Using default SKU.")
            fallback_row = df[(df["SKU No"] == default_sku) & (df["Library"] == active_library)]
            return (fallback_row.iloc[0]["File Name"], fallback_row.iloc[0]["Library"]) if not fallback_row.empty else (None, None)
    except Exception as e:
        print(f"Failed to read SKU mapping file: {e}")
        return None, None
    
class EmittingStream(io.StringIO):
    """Custom stream to capture stdout and stderr logs."""
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def write(self, text):
        super().write(text)
        if self.callback:
            self.callback(text)
 
    def flush(self):
        pass  # Optional: override if needed
    
    def get_logs(self):
        # Return everything written so far
        return self.getvalue()

class ScannerSignalEmitter(QObject):
    vin_scanned = pyqtSignal(str)

class SerialReaderThread(QThread):
    vin_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, port, baudrate):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial_port = None
        self.running = True
        self.max_retries = 3
        self.retry_delay = 1

    def run(self):
        retry_count = 0
        while retry_count < self.max_retries and self.running:
            try:
                print(f"SerialReaderThread: Attempt {retry_count + 1}/{self.max_retries} to open port {self.port} at {self.baudrate} baud")
                self.serial_port = serial.Serial(
                    self.port,
                    self.baudrate,
                    timeout=1,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    bytesize=serial.EIGHTBITS
                )
                print(f"SerialReaderThread: Successfully opened port {self.port}")
                while self.running:
                    if self.serial_port.in_waiting > 0:
                        vin = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                        if vin:
                            print(f"SerialReaderThread: Scanned VIN: {vin}")
                            self.vin_received.emit(vin)
                            break
                    self.msleep(100)
                break
            except serial.SerialException as e:
                retry_count += 1
                error_msg = f"Failed to open port {self.port} on attempt {retry_count}: {str(e)}"
                print(error_msg)
                self.error_occurred.emit(error_msg)
                if retry_count < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    self.error_occurred.emit(f"Serial port {self.port} failed after {self.max_retries} attempts")
            except Exception as e:
                retry_count += 1
                error_msg = f"Unexpected error reading from port {self.port}: {str(e)}"
                print(error_msg)
                self.error_occurred.emit(error_msg)
                if retry_count < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    self.error_occurred.emit(f"Serial port {self.port} failed after {self.max_retries} attempts")
            finally:
                if self.serial_port and self.serial_port.is_open:
                    print(f"SerialReaderThread: Closing port {self.port}")
                    self.serial_port.close()
                    self.serial_port = None

    def stop(self):
        self.running = False
        if self.serial_port and self.serial_port.is_open:
            print(f"SerialReaderThread: Stopping and closing port {self.port}")
            self.serial_port.close()
            self.serial_port = None
        self.quit()
        self.wait()

def load_scanner_config(config_file=resource_path(r"D:\TVS NIRIX Flashing\scanner.ini")):
    config = configparser.ConfigParser()
    config.read(config_file)
    if 'ScannerConfig' not in config:
        return 'AUTO', ['COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8'], 9600
    mode = config.get('ScannerConfig', 'connection_mode', fallback='AUTO').upper()
    ports = config.get('ScannerConfig', 'ports', fallback='COM2,COM3,COM4,COM5,COM6,COM7,COM8').split(',')
    baudrate = config.getint('ScannerConfig', 'baudrate', fallback=9600)
    return mode, ports, baudrate

def load_station_config():
    config = configparser.ConfigParser()
    config_data = {}
    try:
        ini_path = resource_path(r"D:\TVS NIRIX Flashing\station.ini")
        if not os.path.exists(ini_path):
            raise FileNotFoundError(f"station.ini not found at {ini_path}")
        config.read(ini_path)
        if "SETTINGS" in config:
            config_data = dict(config["SETTINGS"])
        else:
            print("No [SETTINGS] section in station.ini")
    except Exception as e:
        print(f"Error reading station.ini: {e}")
    return config_data

class FlashingWorker(QObject):
    progress_changed = pyqtSignal(int, str)  # percentage, status text
    flashing_done = pyqtSignal(bool, str)    # success, message
    flashing_error = pyqtSignal(str)

    def run(self):
        try:
            total_steps = 10
            for step in range(total_steps):
                # Simulate work
                time.sleep(0.5)

                percent = int((step + 1) / total_steps * 100)
                status = f"Flashing step {step + 1} of {total_steps}..."
                self.progress_changed.emit(percent, status)

            # Simulate success
            self.flashing_done.emit(True, "Flashing completed successfully.")

        except Exception as e:
            self.flashing_error.emit(str(e))

class FlashingProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Flashing in Progress")
        self.setModal(True)
        self.setFixedSize(700, 450)

        # Set background color to a light shade
        self.setStyleSheet("background-color: #F0F0F0;")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        # Header label
        self.header_label = QLabel("Flashing", self)
        header_font = QFont("Segoe UI", 18, QFont.Bold)
        self.header_label.setFont(header_font)
        self.header_label.setAlignment(Qt.AlignCenter)
        self.header_label.setStyleSheet("color: #003B6F;")
        self.main_layout.addWidget(self.header_label)

        # Scroll area to hold block progress bars
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFixedHeight(260)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background-color: #D3D3D3; border-radius: 8px;")
        self.main_layout.addWidget(self.scroll_area)

        # Container widget inside scroll area
        self.blocks_container = QWidget()
        self.scroll_area.setWidget(self.blocks_container)

        self.blocks_layout = QVBoxLayout(self.blocks_container)
        self.blocks_layout.setContentsMargins(15, 15, 15, 15)
        self.blocks_layout.setSpacing(18)

        self.block_bars = []
        self.block_labels = []

        # Cancel button layout
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.setFixedSize(120, 40)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF0033;
                color: white;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #e60029;
            }
            QPushButton:pressed {
                background-color: #b20020;
            }
        """)
        btn_layout.addWidget(self.cancel_btn)
        self.main_layout.addLayout(btn_layout)

    def init_progress_bars(self, block_count):
        # Clear previous bars and labels if any
        for i in reversed(range(self.blocks_layout.count())):
            widget_to_remove = self.blocks_layout.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.setParent(None)

        self.block_bars.clear()
        self.block_labels.clear()

        for i in range(block_count):
            block_widget = QWidget()
            block_layout = QHBoxLayout(block_widget)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(20)

            label = QLabel(f"Block {i+1} : ", self)
            label.setFixedWidth(100)
            label_font = QFont("Segoe UI", 14, QFont.Bold)
            label.setFont(label_font)
            label.setStyleSheet("color: #003B6F;")

            progress_bar = QProgressBar(self)
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)
            progress_bar.setTextVisible(True)
            progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            progress_bar.setFixedHeight(28)
            progress_bar.setStyleSheet("""
                QProgressBar {
                    border: 2px solid #003B6F;
                    border-radius: 10px;
                    background-color: #F0F0F0;
                    text-align: center;
                    font-size: 14px;
                    font-weight: bold;
                    color: #003B6F;
                }
                QProgressBar::chunk {
                    background-color: #008000;
                    border-radius: 10px;
                }
            """)

            block_layout.addWidget(label)
            block_layout.addWidget(progress_bar)

            self.blocks_layout.addWidget(block_widget)

            self.block_labels.append(label)
            self.block_bars.append(progress_bar)

    def update_block_progress(self, block_index, chunk_done, total_chunks):
        if 0 <= block_index < len(self.block_bars):
            percent = int((chunk_done / total_chunks) * 100)
            self.block_bars[block_index].setValue(percent)
            self.block_labels[block_index].setText(f"Block {block_index + 1}: {percent}%")
            self.header_label.setText(f"Flashing block {block_index + 1} - {percent}% complete")


class FlashingProgressDialogoldnew(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Flashing in Progress")
        self.setModal(True)
        self.setFixedSize(520, 360)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)
        self.main_layout.setSpacing(15)

        # Header label with bigger bold font
        self.header_label = QLabel("Preparing to flash...", self)
        font = self.header_label.font()
        font.setPointSize(14)
        font.setBold(True)
        self.header_label.setFont(font)
        self.header_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.header_label)

        # Scroll area to hold block progress bars if many blocks
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFixedHeight(220)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.main_layout.addWidget(self.scroll_area)

        # Container widget inside scroll area
        self.blocks_container = QWidget()
        self.scroll_area.setWidget(self.blocks_container)

        self.blocks_layout = QVBoxLayout(self.blocks_container)
        self.blocks_layout.setContentsMargins(10, 10, 10, 10)
        self.blocks_layout.setSpacing(12)

        # Store block progress bars and labels
        self.block_bars = []
        self.block_labels = []

        # Cancel button aligned right
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.setFixedSize(100, 32)
        btn_layout.addWidget(self.cancel_btn)
        self.main_layout.addLayout(btn_layout)

    def init_progress_bars(self, block_count):
        # Clear previous bars/labels if any
        for i in reversed(range(self.blocks_layout.count())):
            widget_to_remove = self.blocks_layout.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.setParent(None)

        self.block_bars.clear()
        self.block_labels.clear()

        for i in range(block_count):
            block_widget = QWidget()
            block_layout = QHBoxLayout(block_widget)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(15)

            label = QLabel(f"Block {i+1}:", self)
            label.setFixedWidth(80)
            progress_bar = QProgressBar(self)
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)
            progress_bar.setTextVisible(True)
            progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            progress_bar.setFixedHeight(24)

            block_layout.addWidget(label)
            block_layout.addWidget(progress_bar)

            self.blocks_layout.addWidget(block_widget)

            self.block_labels.append(label)
            self.block_bars.append(progress_bar)

    def update_block_progress(self, block_index, chunk_done, total_chunks):
        if 0 <= block_index < len(self.block_bars):
            percent = int((chunk_done / total_chunks) * 100)
            self.block_bars[block_index].setValue(percent)
            self.block_labels[block_index].setText(f"Block {block_index + 1}: {percent}%")
            self.header_label.setText(f"Flashing block {block_index + 1} - {percent}% complete")

class FlashingProgressDialogold(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Flashing in Progress")
        self.setModal(True)
        self.setFixedSize(520, 360)

        self.layout = QVBoxLayout(self)

        # Header label
        self.header_label = QLabel("Preparing to flash...", self)
        self.header_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.header_label)

        # Container for per-block progress bars
        self.block_bars = []

        # Cancel button at the bottom
        btn_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        self.layout.addLayout(btn_layout)

    def init_progress_bars(self, total_blocks):
        """Create one progress bar per block."""
        # Remove old bars if any
        for bar in self.block_bars:
            self.layout.removeWidget(bar["label"])
            bar["label"].deleteLater()
            self.layout.removeWidget(bar["progress"])
            bar["progress"].deleteLater()
        self.block_bars.clear()

        for block_index in range(total_blocks):
            label = QLabel(f"Block {block_index + 1}: 0%", self)
            progress_bar = QProgressBar(self)
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)

            self.layout.insertWidget(self.layout.count() - 1, label)      # before cancel button
            self.layout.insertWidget(self.layout.count() - 1, progress_bar)

            self.block_bars.append({
                "label": label,
                "progress": progress_bar
            })

    def update_block_progress(self, block_index, chunks_done, total_chunks):
        """Update progress for a specific block."""
        if 0 <= block_index < len(self.block_bars):
            percent = int((chunks_done / total_chunks) * 100)
            self.block_bars[block_index]["progress"].setValue(percent)
            self.block_bars[block_index]["label"].setText(
                f"Block {block_index + 1}: {percent}% ({chunks_done}/{total_chunks} chunks)"
            )

    def set_header_status(self, status_text):
        """Update the header status message."""
        self.header_label.setText(status_text)

class ApiSelector(QFrame):
    def __init__(self, api_ini_path=resource_path(r"D:\TVS NIRIX Flashing\api.ini"), parent=None):
        super().__init__(parent)
        self.setFixedSize(350, 120)
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
                border: 2px solid #003B6F;
            }
            QLabel {
                color: #003B6F;
                font-family: 'Segoe UI';
                font-weight: bold;
                font-size: 28px;
                border: none;
            }
            QPushButton {
                background-color: #F0F0F0;
                color: black;
                font-size: 26px;
                border: 2px solid #D3D3D3;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                border: 2px solid #FF0033;
                background-color: #ffffff;
            }
            QPushButton:checked {
                background-color: #003B6F;
                color: white;
                border: 2px solid #003B6F;
            }
        """)
        self.api_ini_path = api_ini_path
        self.selected_api = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        #layout.setSpacing(4)

        label = QLabel("Select Mode")
        #label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        #label.setStyleSheet("color: black; background: transparent; border: none; font-size: 30px;")
        
        self.btn_prd = QPushButton("PRD")
        self.btn_ejo = QPushButton("EJO")

        for btn in (self.btn_prd, self.btn_ejo):
            btn.setCheckable(True)

        self.group = QButtonGroup()
        self.group.addButton(self.btn_prd)
        self.group.addButton(self.btn_ejo)

        self.btn_prd.setChecked(True)

        self.btn_prd.clicked.connect(lambda: self.select_api("PRD"))
        self.btn_ejo.clicked.connect(lambda: self.select_api("EJO"))

        btn_layout = QHBoxLayout()
        #btn_layout.setSpacing(10)
        btn_layout.addWidget(self.btn_prd)
        btn_layout.addWidget(self.btn_ejo)

        layout.addWidget(label)
        layout.addLayout(btn_layout)
        
        self.select_api("PRD")

    def select_api(self, name):
        self.selected_api = name.upper()
        
    def get_selected_api(self):
        return self.selected_api
        
    def get_selected_api_url(self, vin=""):
        config = configparser.ConfigParser()
        default_url = "http://10.121.2.107:3000/vehicles/flashFile/prd"
        try:
            if not os.path.exists(self.api_ini_path):
                print(f"[ApiSelector] Error: api.ini not found at {self.api_ini_path}")
                self.parent().instruction_box.append(f"Error: api.ini not found at {self.api_ini_path}. Using default URL.")
                return default_url.rstrip("/") + f"/{vin}" if vin else default_url

            config.read(self.api_ini_path)
            if not config.sections():
                print(f"[ApiSelector] Error: api.ini is empty or corrupted at {self.api_ini_path}")
                self.parent().instruction_box.append(f"Error: api.ini is empty or corrupted. Using default URL.")
                return default_url.rstrip("/") + f"/{vin}" if vin else default_url

            if not self.selected_api:
                print("Selected API not set!")
                self.parent().instruction_box.append("Error: No API mode selected (PRD/EJO). Using default URL.")
                return default_url.rstrip("/") + f"/{vin}" if vin else default_url

            api_key = self.selected_api.upper()
            if "API" not in config or api_key not in config["API"]:
                print(f"Error: Section 'API' or key '{api_key}' not found in {self.api_ini_path}")
                self.parent().instruction_box.append(f"Error: Section 'API' or key '{api_key}' not found in api.ini. Using default URL.")
                return default_url.rstrip("/") + f"/{vin}" if vin else default_url

            base_url = config["API"][api_key]
            if not base_url:
                print(f"Error: Empty URL for key '{api_key}' in {self.api_ini_path}")
                self.parent().instruction_box.append(f"Error: Empty URL for '{api_key}' in api.ini. Using default URL.")
                return default_url.rstrip("/") + f"/{vin}" if vin else default_url

            if vin:
                base_url = base_url.rstrip("/") + f"/{vin}"
            print(f"Selected API URL: {base_url}")
            return base_url
        except Exception as e:
            print(f"[ApiSelector] Error reading '{self.api_ini_path}': {e}")
            self.parent().instruction_box.append(f"Error reading api.ini: {e}. Using default URL.")
            return default_url.rstrip("/") + f"/{vin}" if vin else default_url

class EditableInfoBox(QFrame):
    def __init__(self, label_text: str):
        super().__init__()
        self.setFixedSize(350, 120)
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
                border: 2px solid #003B6F;
            }
            QLabel {
                color: #003B6F;
                font-family: 'Segoe UI';
                font-weight: bold;
                font-size: 28px;
                border: none;
            }
            QLineEdit {
                background-color: #F0F0F0;
                color: black;
                font-size: 26px;
                padding: 8px;
                border: 2px solid #D3D3D3;
                border-radius: 6px;
            }
            QLineEdit:hover {
                border: 2px solid #FF0033;
                background-color: #ffffff;
            }
            QLineEdit:focus {
                border: 2px solid #003B6F;
                background-color: #FFFFFF;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        #layout.setSpacing(4)

        label = QLabel(label_text)
        self.line_edit = QLineEdit()
        #label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        #label.setStyleSheet("color: black; background: transparent; border: none; font-size: 30px;")

        #self.line_edit = QLineEdit()
        #self.line_edit.setStyleSheet("""
        #    background-color: #f0f0f0;
        #    color: black;
        #    border: 1px solid #555;
        #    border-radius: 5px;
        #    padding: 4px;
        #    font-size: 25px;
        #""")
        self.line_edit.setPlaceholderText("Enter Employee No")
        self.line_edit.setValidator(QIntValidator(0, 9999999))
        layout.addWidget(label)
        layout.addWidget(self.line_edit)

    def get_text(self):
        return self.line_edit.text()
    
class HeaderBar(QFrame):
    def __init__(self, logo_path):
        super().__init__()
        self.setFixedHeight(75)
        self.setStyleSheet("""
            QFrame {
                background-color: #003B6F;  /* Smalt Blue */
                border: none;
            }
            QLabel#TitleLabel {
                color: white;
                font-size: 38px;
                font-weight: bold;
                font-family: 'Segoe UI', sans-serif;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(30, 0, 30, 0)
        title_row.setSpacing(0)

        # Left spacer
        title_row.addStretch(2)

        # Center title
        title = QLabel("TVS NIRIX")
        title.setObjectName("TitleLabel")
        title.setAlignment(Qt.AlignCenter)
        title_row.addWidget(title, stretch=4)

        # Right-side logo
        logo_label = QLabel()
        pixmap = QPixmap(logo_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(195, 195, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(pixmap)
        logo_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        title_row.addWidget(logo_label, stretch=2)

        # Add the title row
        main_layout.addLayout(title_row)

        # Full-width red underline (Torch Red)
        underline = QFrame()
        underline.setFixedHeight(5)
        underline.setStyleSheet("background-color: #FF0033; border: none;")
        main_layout.addWidget(underline)

class InfoBox(QFrame):
    def __init__(self, label_text: str, value_text: str):
        super().__init__()
        self.setFixedSize(350, 120)
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
                border: 2px solid #003B6F;
            }
            QLabel {
                color: #003B6F;
                font-family: 'Segoe UI';
                font-weight: bold;
                font-size: 28px;
                background: transparent;
                border: none;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        label = QLabel(label_text)
        #label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        #label.setStyleSheet("color: black; background: transparent; border: none; font-size: 30px;")

        value = QLabel(value_text)
        #value.setFont(QFont("Segoe UI", 9))
        value.setStyleSheet("color: black; background: transparent; border: none; font-size: 30px;")

        layout.addWidget(label)
        layout.addWidget(value)

class CycleTimeBox(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedSize(400, 240)
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
                border: 2px solid #003B6F;
            }
            QLabel {
                background: transparent;
                font-family: 'Segoe UI';
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        #layout.setSpacing(10)

        self.label = QLabel("Cycle Time:")
        self.label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.label.setStyleSheet("color: #003B6F; border:none; font-size: 30px;")
        #self.label.setAlignment(Qt.AlignLeft)

        self.timer_display = QLabel("0 sec")
        self.timer_display.setFont(QFont("Consolas", 28, QFont.Bold))
        self.timer_display.setStyleSheet("color: black; font-size: 45px;")
        self.timer_display.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.label)
        layout.addWidget(self.timer_display)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time)
        self.seconds = 0

    def start_timer(self):
        self.seconds = 0
        self.timer_display.setText("0 sec")
        self.timer.start(1000)

    def stop_timer(self):
        self.timer.stop()

    def reset_timer(self):
        self.seconds = 0
        self.timer_display.setText("0 sec")

    def update_time(self):
        self.seconds += 1
        self.timer_display.setText(f"{self.seconds} sec")

class LabeledEntryBox(QFrame):
    def __init__(self, label_text, placeholder_text="", max_length=100):
        super().__init__()
        self.setFixedSize(450, 120)
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
                border: 2px solid #003B6F;
            }
            QLabel {
                color: #003B6F;
                font-size: 28px;
                font-weight: bold;
                font-family: 'Segoe UI';
                border: none;
            }
            QLineEdit {
                font-size: 26px;
                padding: 8px;
                border: 2px solid #D3D3D3;
                border-radius: 6px;
                background-color: #F0F0F0;
                color: black;
            }
            QLineEdit:hover {
                border: 2px solid #FF0033;
                background-color: white;
            }
            QLineEdit:focus {
                border: 2px solid #003B6F;
                background-color: white;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        self.label = QLabel(label_text)
        #self.label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        #self.label.setStyleSheet("color: black; background: transparent; border: none; font-size: 30px;")
        layout.addWidget(self.label)

        self.entry = QLineEdit()
        self.entry.setPlaceholderText(placeholder_text)
        self.entry.setMaxLength(max_length)
        layout.addWidget(self.entry)

    def set_value(self, text):
        self.entry.setText(text)

    def get_value(self):
        return self.entry.text()

class ActiveLibrarySelector(QFrame):
    def __init__(self, library_list, default_value=None):
        super().__init__()
        self.setFixedSize(950, 120)
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 15px;
                border:2px solid #003B6F;
            }
            QLabel {
                color: #003B6F;
                font-size: 28px;
                font-weight: bold;
                font-family: 'Segoe UI';
                border:none;
            }
            QComboBox {
                font-size: 26px;
                padding: 6px;
                border-radius: 6px;
                background-color: #F0F0F0;
                color: black;
                border: 2px solid #D3D3D3;
            }
            QComboBox:hover {
                border: 2px solid #FF0033;
                background-color: white;
            }
            QComboBox:focus {
                border: 2px solid #003B6F;
                background-color: white;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                selection-background-color: #818689;
                selection-color: white; 
                color: black;
                border: 1px solid #003B6F;
                font-size: 24px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        #layout.setSpacing(6)

        self.label = QLabel("Active Library")
        layout.addWidget(self.label)

        self.combo = QComboBox()
        self.combo.addItems(library_list)

        if default_value and default_value in library_list:
            self.combo.setCurrentText(default_value)
        else:
            self.combo.setCurrentIndex(0)

        layout.addWidget(self.combo)
        self.combo_box = self.combo
        self.combo.currentTextChanged.connect(self.lock_selection)
        self.selection_locked = False

    def lock_selection(self, library):
        if not self.selection_locked:
            self.selection_locked = True
            self.save_to_station_ini(library)
            print(f"Active library updated to: {library}")

    def save_to_station_ini(self, library):
        config = configparser.ConfigParser()
        ini_path = resource_path(r"D:\TVS NIRIX Flashing\station.ini")
        try:
            config.read(ini_path)
            if "SETTINGS" not in config:
                config["SETTINGS"] = {}
            config["SETTINGS"]["active_library"] = library
            with open(ini_path, 'w') as configfile:
                config.write(configfile)
            print(f"Saved active_library '{library}' to {ini_path}")
        except Exception as e:
            print(f"Failed to save active_library to station.ini: {e}")

    def get_selected_library(self):
        return self.combo.currentText()

class MainWindow(QWidget):
    sku_fetched = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.cycle_time_box = CycleTimeBox()
        self.sku = None
        self.test_cycle_completed = False
        self.test_boxes = []
        self.sku_fetched.connect(self.on_sku_fetched)
        
        self.retry_count = 0
        self.max_retries = 3
        self.global_retry_count = 0
        self.max_global_retries = 3
        self.worker_thread = None
        self.worker = None
        self.result = None
        self.test_duration = 0
        self.test_results = []
        
        header_bar = HeaderBar(resource_path("TVS logo white.png"))

        log_folder = resource_path(r"D:\TVS NIRIX Flashing\test_results")
        try:
            log_cleanup_module = importlib.import_module("log_cleanup")
            log_cleanup_module.cleanup_old_logs(log_folder)
        except ImportError as e:
            print(f"Failed to import log_cleanup.py: {e}")
        except AttributeError as e:
            print(f"Failed to call cleanup_old_logs in log_cleanup.py: {e}")
        except Exception as e:
            print(f"Error executing log_cleanup.py: {e}")

        self.setWindowTitle("TVS NIRIX")
        self.setStyleSheet("background-color: white;")
        self.setWindowState(Qt.WindowMaximized)
        screen = QApplication.desktop().screenGeometry()
        self.setGeometry(0, 0, screen.width(), screen.height())
        self.setWindowFlags(self.windowFlags() & ~Qt.FramelessWindowHint)

        pc_name = socket.gethostname()
        config_data = load_station_config()
        operation_number = config_data.get("operation_no", "N/A")

        top_row = QHBoxLayout()
        top_row.setSpacing(20)
        top_row.setContentsMargins(20, 20, 20, 0)

        program_box = InfoBox("Flashing", "0825_V1.6")
        self.cycle_time_box = CycleTimeBox()
        pc_box = InfoBox("PC Name:", pc_name)
        op_box = InfoBox("Operation No:", operation_number)
        emp_box = EditableInfoBox("Emp No:")
        self.api_selector = ApiSelector(parent=self)

        top_row.addWidget(program_box)
        top_row.addWidget(pc_box)
        top_row.addWidget(op_box)
        top_row.addWidget(emp_box)
        top_row.addWidget(self.api_selector)
        top_row.addStretch(1)

        second_row = QHBoxLayout()
        second_row.setContentsMargins(20, 10, 20, 20)

        self.vin_box = LabeledEntryBox("Identifier Number:", "Eg: MD612345678912345", max_length=17)
        self.vin_input = self.vin_box.entry
        self.vin_input.installEventFilter(self)
        self.vin_input.returnPressed.connect(self.start_test_cases)

        self.second_sub_box = LabeledEntryBox("Part Number:", "SKU", max_length=10)

        side_vbox = QVBoxLayout()
        side_vbox.addWidget(self.vin_box)
        side_vbox.addWidget(self.second_sub_box)
        side_vbox.addStretch()

        station_config = load_station_config()
        active_library_default = station_config.get("active_library", "Flashing")
        available_libraries = ["Flashing", "3W_Battery_Healthcheck", "3W_Diagnostics", "TPMS", "IVCU"]
        self.active_library_selector = ActiveLibrarySelector(available_libraries, active_library_default)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                color: black;
                border: 2px solid #003B6F;
                border-radius: 15px;
                text-align: center;
                height: 30px;
                font-size: 40px;
                width: 100%;
            }
            QProgressBar::chunk {
                background-color: #008000;
                border-radius: 15px;
            }
        """)

        side_active_process_bar_box = QVBoxLayout()
        side_active_process_bar_box.addWidget(self.active_library_selector)
        side_active_process_bar_box.addSpacing(40)
        side_active_process_bar_box.addWidget(self.progress_bar)
        side_active_process_bar_box.addStretch()

        second_row.addWidget(self.cycle_time_box)
        second_row.addLayout(side_vbox)
        second_row.addLayout(side_active_process_bar_box)
        second_row.addStretch()

        third_row = QHBoxLayout()
        third_row.setContentsMargins(20, 0, 20, 20)

        self.test_table = QTableWidget()
        self.test_table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #c9ccce;
                color: black;
                font-size: 24px;
                font-family: 'Segoe UI', sans-serif;
                border: none;
                border-radius: 12px;
                gridline-color: transparent;  
                selection-background-color: #FF0033;  /* torch red */
                selection-color: white;
            }
        
            QHeaderView::section {
                background-color: #003B6F;  /* smalt blue */
                color: white;
                font-size: 26px;
                font-weight: bold;
                padding: 12px;
                border: none;
                border-bottom: 2px solid #FF0033;
            }
        
            QTableWidget::item {
                padding: 14px;
                border: none;
            }
        
            QTableWidget::item:hover {
                background-color: #f5f5f5;
            }
        
            QTableWidget::item:selected {
                background-color: #FF0033;
                color: white;
            }
        
            QScrollBar:vertical {
                border: none;
                background: #e0e0e0;
                width: 18px;
                margin: 2px 0 2px 0;
                border-radius: 9px;
            }
        
            QScrollBar::handle:vertical {
                background: #003B6F;
                min-height: 25px;
                border-radius: 9px;
            }
        
            QScrollBar::handle:vertical:hover {
                background: #0055aa;
            }
        
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
                subcontrol-origin: margin;
            }
        
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        
            QScrollBar:horizontal {
                border: none;
                background: #e0e0e0;
                height: 18px;
                margin: 0px 2px 0px 2px;
                border-radius: 9px;
            }
        
            QScrollBar::handle:horizontal {
                background: #003B6F;
                min-width: 25px;
                border-radius: 9px;
            }
        
            QScrollBar::handle:horizontal:hover {
                background: #0055aa;
            }
        
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
                subcontrol-origin: margin;
            }
        
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)
        
        self.test_table.setAlternatingRowColors(True)
        self.test_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.test_table.verticalHeader().setVisible(False)
        self.test_table.verticalHeader().setDefaultSectionSize(60)
        self.test_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.test_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.test_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.test_table.setMinimumHeight(400)
        self.test_table.setMaximumHeight(800)
        
        self.pass_image_label = QLabel()
        self.fail_image_label = QLabel()
        
        self.pass_image_label.setFixedSize(120, 120)
        self.fail_image_label.setFixedSize(120, 120)
        
        self.pass_image_label.setScaledContents(True)
        self.fail_image_label.setScaledContents(True)
        
        # Initially hide both
        self.pass_image_label.hide()
        self.fail_image_label.hide()
        
        common_textedit_style = ("""
            QTextEdit {
                background-color: white;
                color: #1a1a1a;
                font-size: 20px;
                font-weight: bold;
                border: 2px solid #003B6F;
                border-radius: 12px;
                padding: 10px;
            }
            
            QTextEdit:hover {
                background-color: #f1f1f1;
            }
            
            QScrollBar:vertical {
                border: none;
                background: #e0e0e0;
                width: 18px;
                margin: 2px 0 2px 0;
                border-radius: 9px;
            }
            
            QScrollBar::handle:vertical {
                background: #003B6F;
                min-height: 25px;
                border-radius: 9px;
            }
            
            QScrollBar::handle:vertical:hover {
                background: #0055aa;
            }
            
            QScrollBar:horizontal {
                border: none;
                background: #e0e0e0;
                height: 18px;
                margin: 0px 2px 0px 2px;
                border-radius: 9px;
            }
            
            QScrollBar::handle:horizontal {
                background: #003B6F;
                min-width: 25px;
                border-radius: 9px;
            }
            
            QScrollBar::handle:horizontal:hover {
                background: #0055aa;
            }
            """)
        
        instruction_label = QLabel("Instructions:")
        #instruction_label.setStyleSheet("color: black; font-size: 25px; font-weight: bold; margin-bottom: 5px;")
        instruction_label.setStyleSheet("color: #003D6F; font-size: 28px; font-weight: bold; margin-bottom: 5px;")


        self.instruction_box = QTextEdit()
        self.instruction_box.setReadOnly(True)
        self.instruction_box.setStyleSheet(common_textedit_style)
        self.instruction_box.setPlaceholderText("Instructions will appear here...")
        self.instruction_box.setMinimumWidth(300)

        result_label = QLabel("Result:")
        #result_label.setStyleSheet("color: black; font-size: 25px; font-weight: bold; margin-bottom: 5px;")
        result_label.setStyleSheet("color: #003D6F; font-size: 28px; font-weight: bold; margin-bottom: 5px;")


        self.result_box = QTextEdit()
        self.result_box.setReadOnly(True)
        self.result_box.setStyleSheet(common_textedit_style)
        self.result_box.setPlaceholderText("Result will appear here...")
        self.result_box.setMinimumWidth(300)

        instruction_result_layout = QVBoxLayout()
        instruction_result_layout.addWidget(instruction_label)
        instruction_result_layout.addWidget(self.instruction_box, stretch=1)
        instruction_result_layout.addWidget(result_label)
        instruction_result_layout.addWidget(self.result_box, stretch=1)
        instruction_result_layout.addStretch()
        instruction_result_layout.addWidget(self.pass_image_label, alignment=Qt.AlignRight)
        instruction_result_layout.addWidget(self.fail_image_label, alignment=Qt.AlignRight)

        third_row.addWidget(self.test_table, stretch=2)
        third_row.addSpacing(20)
        third_row.addLayout(instruction_result_layout, stretch=1)
        
        # ----- Footer Label -----
        footer_label = QLabel("2025 PED@CT&T. All rights reserved.")
        footer_label.setAlignment(Qt.AlignCenter)
        footer_label.setFixedHeight(40)  # Adjust the height as needed
        footer_label.setStyleSheet("""
            background-color: #003D6F;
            color: white;
            font-size: 11pt;
            padding-top: 8px;
        """)

        main_layout = QVBoxLayout()
        main_layout.addWidget(header_bar)
        self.active_library_selector.combo_box.currentTextChanged.connect(self.on_active_library_changed)
        main_layout.addLayout(top_row)
        main_layout.addLayout(second_row)
        main_layout.addLayout(third_row, stretch=1)
        main_layout.addWidget(footer_label)
        self.setLayout(main_layout)
        self.load_tests_from_sku("GE190510", self.active_library_selector.get_selected_library())

        self.scanner_signals = ScannerSignalEmitter()
        self.scanner_signals.vin_scanned.connect(self.handle_scanned_vin)

        connection_mode, ports, baudrate = load_scanner_config()
        self.connection_mode = connection_mode
        self.ports = ports
        self.baudrate = baudrate
        self.serial_reader_thread = None
        self.hid_thread = None
        self.scanner_mode = None
        self.detect_scanner_mode()
        self.prepare_for_next_cycle()

    def detect_scanner_mode(self):
        ports = serial.tools.list_ports.comports()
        available_ports = [p.device for p in ports]
        print(f"Available COM ports: {available_ports}")
        if any(port in available_ports for port in self.ports):
            self.scanner_mode = "CDC"
            print(f"Scanner detected in CDC mode on ports: {available_ports}")
            return
        devices = usb.core.find(find_all=True)
        for dev in devices:
            if dev.bDeviceClass == 3:
                self.scanner_mode = "HID"
                print("Scanner detected in HID mode")
                return
        print("No scanner detected in CDC or HID mode")
        self.scanner_mode = None

    def start_com_scanner(self):
        ports = serial.tools.list_ports.comports()
        available_ports = [p.device for p in ports]
        print(f"Checking ports: {self.ports}, Available: {available_ports}")

        usb_serial_ports = []
        for port in ports:
            if port.device in self.ports and ("USB" in port.description or "CDC" in port.description):
                usb_serial_ports.append(port.device)

        if not usb_serial_ports:
            print("No USB serial ports available")
            return

        max_retries = 3
        scanner_started = False

        for port in usb_serial_ports:
            for attempt in range(max_retries):
                try:
                    if self.serial_reader_thread:
                        print(f"Stopping previous serial reader thread before trying {port}")
                        self.serial_reader_thread.stop()
                        self.serial_reader_thread.wait()

                    self.serial_reader_thread = SerialReaderThread(port, self.baudrate)
                    self.serial_reader_thread.vin_received.connect(self.handle_scanned_vin)
                    self.serial_reader_thread.start()

                    print(f"CDC Scanner started on port {port} (attempt {attempt + 1})")
                    scanner_started = True
                    break

                except PermissionError as pe:
                    print(f"PermissionError on {port} (attempt {attempt + 1}): {pe}")
                except Exception as e:
                    print(f"Attempt {attempt + 1}/{max_retries} on {port} failed: {e}")

                time.sleep(1)

            if scanner_started:
                break

        if not scanner_started:
            print("All attempts failed on all USB serial ports.")

    def start_hid_scanner(self):
        def read_hid_input():
            try:
                vin = ""
                while True:
                    char = sys.stdin.read(1)
                    if char == '\r' or char == '\n':
                        if vin:
                            print(f"HID Scanner: Scanned VIN: {vin}")
                            self.scanner_signals.vin_scanned.emit(vin)
                            break
                    elif char == '\b':
                        vin = vin[:-1]
                    elif char.isalnum():
                        vin += char
            except Exception as e:
                print(f"HID Scanner error: {e}")

        self.hid_thread = threading.Thread(target=read_hid_input, daemon=True)
        self.hid_thread.start()
        print("Started HID scanner")

    def handle_scanned_vin(self, vin):
        print(f"handle_scanned_vin: Received VIN: {vin}")
        self.vin_input.setText(vin)
        self.vin_input.repaint()
        self.start_test_cases()
        if self.serial_reader_thread:
            print("handle_scanned_vin: Stopping serial reader thread")
            self.serial_reader_thread.stop()
            self.serial_reader_thread = None
        if self.hid_thread:
            print("handle_scanned_vin: Stopping HID reader thread")
            self.hid_thread = None

    def eventFilter(self, source, event):
        if source == self.vin_input and event.type() == event.FocusIn:
            self.detect_scanner_mode()
            if self.scanner_mode == "CDC":
                if self.serial_reader_thread:
                    print("eventFilter: Stopping existing serial reader thread")
                    self.serial_reader_thread.stop()
                self.start_com_scanner()
            elif self.scanner_mode == "HID":
                if self.hid_thread:
                    print("eventFilter: Stopping existing HID reader thread")
                    self.hid_thread = None
                self.start_hid_scanner()
        return super().eventFilter(source, event)
    
    def on_active_library_changed(self):
        active_library = self.active_library_selector.get_selected_library()
    
        if active_library == "3W_Battery_Healthcheck":
            self.vin_input.setPlaceholderText("Enter 12-digit Battery Number")
            self.api_selector.setDisabled(True)
            self.second_sub_box.setDisabled(True)
        else:
            self.vin_input.setPlaceholderText("Scan 17-digit VIN starting with MD6")
            self.api_selector.setDisabled(False)
            self.second_sub_box.setDisabled(False)
        if active_library == "3W_Battery_Healthcheck":
            self.vin_input.setMaxLength(12)
        else:
            self.vin_input.setMaxLength(17)


    def prepare_for_next_cycle(self):
        self.vin_input.clear()
        self.vin_input.setFocus()
        self.detect_scanner_mode()
        if self.scanner_mode == "CDC":
            self.start_com_scanner()
        elif self.scanner_mode == "HID":
            self.start_hid_scanner()
        else:
            print("No Scanner Detected")
        self.on_active_library_changed()

    def reset_for_next_cycle(self):
        print("Resetting for next cycle...")
        self.current_test_index = 0
        self.test_results = []
        self.test_times = []
        self.final_status = "OK"
        self.vin_input.setText("")
        self.progress_bar.setValue(0)
        self.vin_input.clearFocus()
        self.vin_input.setFocus()
        self.second_sub_box.entry.setText("")
        self.instruction_box.clear()
        self.instruction_box.append("Scan VIN to start next test cycle...")
        self.result_box.clear()
        self.start_time = None
        self.cycle_time_box.stop_timer()
        self.cycle_time_box.reset_timer()
        for row in range(self.test_table.rowCount()):
            for col in range(self.test_table.columnCount()):
                item = self.test_table.item(row, col)
                if item:
                    item.setBackground(QColor("#ffffff"))
                    item.setForeground(QColor("black"))
        for row in range(self.test_table.rowCount()):
            self.test_table.setItem(row, self.test_table.columnCount() - 2, QTableWidgetItem(""))
            self.test_table.setItem(row, self.test_table.columnCount() - 1, QTableWidgetItem(""))
            self.test_table.removeCellWidget(row, self.test_table.columnCount() - 1)
        self.test_cases = []
        self.current_test_index = 0
        self.sku = None
        self.json_response = None
        self.test_failed = False
        self.test_table.verticalScrollBar().setValue(0)
        importlib.invalidate_caches()
        active_library = self.active_library_selector.get_selected_library()
        for module_name in list(sys.modules.keys()):
            if module_name.startswith(active_library):
                del sys.modules[module_name]
                print(f"Cleared module: {module_name}")
        if self.serial_reader_thread:
            print("reset_for_next_cycle: Stopping serial reader thread")
            self.serial_reader_thread.stop()
            self.serial_reader_thread = None
        if self.hid_thread:
            print("reset_for_next_cycle: Stopping HID reader thread")
            self.hid_thread = None
        try:
            import can
            can.rc['interface'] = 'pcan'
            can.rc['channel'] = 'PCAN_USBBUS1'
            bus = can.interface.Bus()
            bus.shutdown()
            print("CAN bus successfully shut down")
        except Exception as e:
            print(f"Failed to shut down CAN bus: {e}")
        self.prepare_for_next_cycle()
        
    def run_flashing_process(self, row):
        """Run full flashing process in main GUI thread with multiple block progress bars."""
        mot_file = r"D:\TVS NIRIX Flashing\N6060929_02 1.mot"
    
        # 1. Show flashing dialog
        dialog = FlashingProgressDialog(self)
    
        # Step 1 — Get block info
        try:
            sys.path.insert(0, r'D:\TVS_NIRIX_Flashing')

            from Flashing.find_addr_len import find_addr_len
            from Flashing.flash_setup import flash_setup
            from Flashing.flash_chunk import flash_chunk
            from Flashing.flashing_done import flashing_done
        except ImportError as e:
            self._handle_flashing_result(False, f"Import error: {e}",row)
            return
    
        try:
            # Get list of (start_address, length) for each block
            blocks = find_addr_len(mot_file)  
            total_blocks = len(blocks)
            print(blocks)
    
            if total_blocks == 0:
                self._handle_flashing_result(False, "No blocks found for flashing",row)
                return
    
            # Initialize dialog with multiple progress bars — one per block
            dialog.init_progress_bars(total_blocks)
            dialog.show()
            QApplication.processEvents()
    
            # Step 2 — Loop through each block
            for block_index, (start_addr, length) in enumerate(blocks):
                QApplication.processEvents()
    
                # Get chunk details for this block
                chunk_size, num_chunks = flash_setup(start_addr, length)
    
                if num_chunks <= 0:
                    self._handle_flashing_result(False, f"Invalid chunk count for block {block_index + 1}", row)
                    return
    
                # Step 3 — Flash each chunk in this block
                chunk_counter = 0
                success = True
                crc_value = None
                gen = flash_chunk(mot_file, start_addr, length, chunk_size)
                for seq in gen:
                    if isinstance(seq, bool):  # chunk progress
                        chunk_counter += 1
                        dialog.update_block_progress(block_index, chunk_counter, num_chunks)
                        QApplication.processEvents()
                    elif isinstance(seq, tuple) and seq[0] == "DONE":
                        _, success, crc_value = seq  # final return (True, crc)
                
                if not success:
                    self._handle_flashing_result(
                        False, f"Flashing failed at block {block_index + 1}", row
                    )
                    dialog.reject()
                    return
                
                # ✅ Step 3.5 — Run flash validation
                if not flashing_done(start_addr, length, crc_value):
                    self._handle_flashing_result(False, "Flash validation failed", row)
                    dialog.reject()
                    return
    
            # Step 4 — All blocks completed
            dialog.accept()
            self._handle_flashing_result(True, "True", row)
            self.instruction_box.clear()
            self.instruction_box.append("Flashing completed successfully")
    
        except Exception as e:
            dialog.reject()
            self._handle_flashing_result(False, f"Flashing process failed: {str(e)}", row)
    
    def _handle_flashing_result(self, success, message, row):
        """Update your main test logic with flashing results."""
        status = "PASSED" if success else "FAILED"
        color = "#008000" if success else "red"
    
        self.update_test_result_row(row, message, status)
        self.result_box.setText(
            f'<span style="color:{color}; font-weight:bold; font-size:24px;">Flashing - {status}</span>'
        )
        self.progress_bar.setValue(int(((self.current_test_index + 1) / len(self.test_cases)) * 100))
    
        # Continue to next test
        QTimer.singleShot(1000, self._proceed_to_next_test)

    def update_test_result_row(self, row_index, actual_value, result):
        active_library = self.active_library_selector.get_selected_library()
        actual_value_col = 6 if active_library in ["3W_Diagnostics", "3W_Battery_Healthcheck", "Flashing"] else 3
        result_col = 7 if active_library in ["3W_Diagnostics", "3W_Battery_Healthcheck", "Flashing"] else 4
    
        # Set the actual value as normal
        self.test_table.setItem(row_index, actual_value_col, QTableWidgetItem(str(actual_value)))
    
        # Create QLabel with icon
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
    
        if str(result).upper() in ["PASS", "PASSED"]:
            pixmap = QPixmap(resource_path("Pass picture.png"))
        elif str(result).upper() in ["FAIL", "FAILED"]:
            pixmap = QPixmap(resource_path("fail picture.png"))
        else:
            pixmap = QPixmap()
    
        # Resize image
        pixmap = pixmap.scaled(70, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(pixmap)
    
        # Remove any existing widget or item from that cell
        self.test_table.removeCellWidget(row_index, result_col)
    
        # Set custom widget in the result column
        self.test_table.setCellWidget(row_index, result_col, label)
    
    def on_sku_changed(self, new_sku):
        active_library = self.active_library_selector.get_selected_library()
        self.load_tests_from_sku(new_sku, active_library)

    def load_tests_from_sku(self, sku_number, active_library):
        active_library = self.active_library_selector.get_selected_library()
        if active_library == "3W_Battery_Healthcheck":
            battery_number = self.vin_input.text().strip()
            if not battery_number:
                return
            if len(battery_number) != 12:
                self.instruction_box.append("Invalid Battery Number. Please enter a 12-digit number.")
                return
        
            battery_name = self.get_battery_name_dynamic(battery_number)
        
            if not battery_name:
                self.instruction_box.append("No mapping found for this battery number prefix.")
                return
        
            test_file_name = f"{battery_name} - details.xlsx"
            full_path = resource_path(os.path.join("Battery Specification", test_file_name))

        else:
            print(f"Loading tests for SKU: {sku_number}, Library: {active_library}")
            active_library = self.active_library_selector.get_selected_library()
            test_file_name = f"{sku_number} - Flashing - details.xlsx"
            full_path = resource_path(os.path.join("sku_files", test_file_name))

        if not os.path.isfile(full_path):
            print(f"[ERROR] Test file not found: {full_path}")
            self.instruction_box.append(f"Test file for SKU '{sku_number}' not found.")
            self.test_table.setRowCount(0)
            return

        try:
            df = pd.read_excel(full_path, engine="openpyxl", keep_default_na=False)
        except Exception as e:
            print(f"Failed to read test file: {e}")
            self.instruction_box.append(f"Failed to read test file: {e}")
            self.test_table.setRowCount(0)
            return

        self.test_table.setRowCount(0)

        if active_library in ["3W_Diagnostics", "3W_Battery_Healthcheck", "Flashing"]:
            self.test_table.setColumnCount(8)
            self.test_table.setHorizontalHeaderLabels([
                "S.No", "Test Sequence", "Parameter", "Value", "LSL", "USL", "Actual Value", "Result"
            ])
            self.test_table.setColumnWidth(0, 60)
            self.test_table.setColumnWidth(1, 250)
            self.test_table.setColumnWidth(2, 150)
            self.test_table.setColumnWidth(3, 150)
            self.test_table.setColumnWidth(4, 100)
            self.test_table.setColumnWidth(5, 100)
            self.test_table.setColumnWidth(6, 200)
            self.test_table.setColumnWidth(7, 200)
        else:  # TPMS
            self.test_table.setColumnCount(5)
            self.test_table.setHorizontalHeaderLabels([
                "S.No", "Test Sequence", "Parameter", "Actual Value", "Result"
            ])
            self.test_table.setColumnWidth(0, 60)
            self.test_table.setColumnWidth(1, 400)
            self.test_table.setColumnWidth(2, 250)
            self.test_table.setColumnWidth(3, 250)
            self.test_table.setColumnWidth(4, 200)

        for idx, row in df.iterrows():
            self.test_table.insertRow(idx)
            columns = ["S.No", "Test Sequence", "Parameter", "Value", "LSL", "USL"] if active_library in ["3W_Diagnostics","3W_Battery_Healthcheck"] else ["S.No", "Test Sequence", "Parameter"]
            for col_idx, key in enumerate(columns):
                self.test_table.setItem(idx, col_idx, QTableWidgetItem(str(row.get(key, ''))))
                
            # Add empty items for 'Actual Value' and 'Result' to avoid NoneType errors
            self.test_table.setItem(idx, 6, QTableWidgetItem(""))  # Actual Value
            self.test_table.setItem(idx, 7, QTableWidgetItem(""))  # Result
            
    def get_battery_name_dynamic(self, battery_number):
        mapping_file = resource_path(r"D:\TVS NIRIX Flashing\Battery Mapping.xlsx")
        try:
            df = pd.read_excel(mapping_file, engine="openpyxl", keep_default_na=False)
    
            # Ensure correct column names
            df.columns = [str(col).strip().replace('\u200b', '') for col in df.columns]
            if "Battery Type" not in df.columns or "Battery Name" not in df.columns:
                raise ValueError("Battery Mapping file is missing required columns.")

            # Take first 3 characters of battery_number
            prefix = battery_number[:3]
    
            # Find matching row
            row = df[df["Battery Type"] == prefix]
            if not row.empty:
                return row.iloc[0]["Battery Name"]
    
        except Exception as e:
            print(f"[ERROR] Failed to load battery mapping: {e}")
            self.instruction_box.append(f"Error reading Battery Mapping: {e}")    
        return None
    
    def append_to_log_file(self, text):
        """Thread-safe log collector for test result capturing."""
        if not hasattr(self, "current_test_log"):
            self.current_test_log = ""   
        self.current_test_log += text
        
    def fetch_sku_from_api(self, vin, base_url):
        def api_task():
            url = base_url
            max_attempts = 3
            default_sku = "GE190510"
            selected_mode = self.api_selector.get_selected_api()
            mode_display = "Production (PRD)" if selected_mode == "PRD" else "Engineering Job Order (EJO)"
            active_library = self.active_library_selector.get_selected_library()
            for attempt in range(1, max_attempts + 1):
                try:
                    print(f"Attempt {attempt}: Sending API request to {url}")
                    response = requests.get(url, timeout=5)
                    print(f"API returned status code {response.status_code}")
                    if response.status_code == 200:
                        json_data = response.json()
                        self.json_response = json_data
                        modules = json_data.get("data", {}).get("modules", [])
                        sku_found = False
                        for module in modules:
                            configs = module.get("configs", [])
                            for config in configs:
                                if config.get("refname") == "PCM_SKU_WRITE":
                                    messages = config.get("messages", [])
                                    for msg in messages:
                                        if msg.get("refname") == "SKU_WRITE":
                                            sku = msg.get("txbytes")
                                            if sku:
                                                print(f"[SKU fetched: {sku}]")
                                                # Validate SKU library against active library
                                                file_name, sku_library = get_file_name_from_sku(sku, active_library)
                                                if sku_library and sku_library != active_library:
                                                   # print(f"VIN {vin} SKU {sku} belongs to library {sku_library}, but active library is {active_library}")
                                                    self.instruction_box.append(
                                                        f'<span style="color:red;">Scanned VIN number is not in Selected Active Library ({active_library}).</span>'
                                                    )
                                                    self.vin_input.setText("")
                                                    self.vin_input.setFocus()
                                                    self.cycle_time_box.stop_timer()
                                                    self.cycle_time_box.reset_timer()
                                                    return
                                                if file_name:
                                                    self.sku = sku
                                                    self.sku_fetched.emit(sku)
                                                    return
                                                else:
                                                    #print(f"No valid file for SKU {sku} in any library")
                                                    self.instruction_box.append(
                                                        f'<span style="color:red;">No valid test file for SKU {sku}.</span>'
                                                    )
                                                    self.vin_input.setText("")
                                                    self.vin_input.setFocus()
                                                    self.cycle_time_box.stop_timer()
                                                    self.cycle_time_box.reset_timer()
                                                    return
                                            sku_found = True
                        if not sku_found:
                           # print(f"Scanned VIN number {vin} does not belong to the selected API mode: {mode_display}")
                            self.instruction_box.append(
                                f'<span style="color:red;">Scanned VIN number is not in Selected API Mode: ({mode_display}).</span>'
                            )
                            self.vin_input.setText("")
                            self.vin_input.setFocus()
                            self.cycle_time_box.stop_timer()
                            self.cycle_time_box.reset_timer()
                            return
                    elif response.status_code == 404:
                       # print(f"Scanned VIN number {vin} does not belong to the selected API mode: {mode_display}")
                        self.instruction_box.append(
                                f'<span style="color:red;">Scanned VIN number is not in Selected API Mode: ({mode_display}).</span>'
                        )
                        self.vin_input.setText("")
                        self.vin_input.setFocus()
                        self.cycle_time_box.stop_timer()
                        self.cycle_time_box.reset_timer()
                        return
                    else:
                        #print(f"API returned unexpected status: {response.status_code}")
                        self.instruction_box.append(f"API returned unexpected status: {response.status_code}")
                except requests.RequestException as e:
                   # print(f"API attempt {attempt} failed: {e}")
                    self.instruction_box.append(f"API attempt {attempt} failed: {e}")
                time.sleep(1)
           # print(f"API call failed after {max_attempts} attempts. Using default SKU: {default_sku}")
            self.instruction_box.append(f"API call failed after {max_attempts} attempts. Using default SKU: {default_sku}")
            file_name, sku_library = get_file_name_from_sku(default_sku, active_library)
            if sku_library and sku_library != active_library:
               # print(f"Default SKU {default_sku} belongs to library {sku_library}, but active library is {active_library}")
                self.instruction_box.append(
                    f'<span style="color:red;">Vin number is not the selected active library ({active_library}).</span>'
                )
                self.vin_input.setText("")
                self.vin_input.setFocus()
                self.cycle_time_box.stop_timer()
                self.cycle_time_box.reset_timer()
                return
            self.json_response = None
            self.sku = default_sku
            self.sku_fetched.emit(default_sku)
        threading.Thread(target=api_task, daemon=True).start()

    def fetch_sku_from_api_old(self, vin, base_url):
        def api_task():
            url = base_url
            max_attempts = 3
            default_sku = "GE190510"
            for attempt in range(1, max_attempts + 1):
                try:
                    print(f"Attempt {attempt}: Sending API request to {url}")
                    response = requests.get(url, timeout=5)
                    print(f"API returned status code {response.status_code}")
                    if response.status_code == 200:
                        json_data = response.json()
                        self.json_response = json_data
                        modules = json_data.get("data", {}).get("modules", [])
                        for module in modules:
                            configs = module.get("configs", [])
                            for config in configs:
                                if config.get("refname") == "PCM_SKU_WRITE":
                                    messages = config.get("messages", [])
                                    for msg in messages:
                                        if msg.get("refname") == "SKU_WRITE":
                                            sku = msg.get("txbytes")
                                            if sku:
                                                print(f"[SKU fetched: {sku}")
                                                self.sku = sku
                                                self.sku_fetched.emit(sku)
                                                return
                    elif response.status_code == 404:
                        print("Scanned VIN number is not in Selected Mode: 404 Not Found")
                        self.instruction_box.append(f"API returned 404: VIN {vin} not found in selected mode.")
                        break
                    else:
                        print(f"API returned unexpected status: {response.status_code}")
                except requests.RequestException as e:
                    print(f"API attempt {attempt} failed: {e}")
                    self.instruction_box.append(f"API attempt {attempt} failed: {e}")
                time.sleep(1)
            print(f"API call failed after {max_attempts} attempts. Using default SKU: {default_sku}")
            self.instruction_box.append(f"API call failed after {max_attempts} attempts. Using default SKU: {default_sku}")
            self.json_response = None
            self.sku = default_sku
            self.sku_fetched.emit(default_sku)
        threading.Thread(target=api_task, daemon=True).start()

    def parse_test_file(self, file_path):
        try:
            df = pd.read_excel(file_path, engine="openpyxl", keep_default_na=False)
            if "Test Sequence" not in df.columns:
                self.instruction_box.append("No test sequence")
                print("[ERROR] 'Test Sequence' column missing in Excel.")
                return []
            test_cases = []
            for test_name in df["Test Sequence"].dropna():
                clean_name = str(test_name).strip().replace(" ", "_")
                test_cases.append((clean_name, clean_name))
            return test_cases
        except Exception as e:
            print(f"[ERROR] Failed to parse test file '{file_path}': {e}")
            return []

    def on_sku_fetched(self, sku):
        active_library = self.active_library_selector.get_selected_library()
    
        # === NEW FLOW for Battery Healthcheck ===
        if active_library == "3W_Battery_Healthcheck":
            battery_number = self.vin_input.text()
            # Use helper function to resolve battery name from mapping file
            battery_name = self.get_battery_name_dynamic(battery_number)
            if not battery_name:
                self.instruction_box.append(f"No battery mapping found for number: {battery_number}")
                return
    
            test_file_name = f"{battery_name} - details.xlsx"
            full_path = resource_path(os.path.join("Battery Specification", test_file_name))
            print(f"[DEBUG] Battery name resolved: {battery_name}")
            print(f"[DEBUG] Battery test file path: {full_path}")
    
            if not os.path.exists(full_path):
                self.instruction_box.append(f"Test file '{test_file_name}' not found in Battery Specification folder.")
                self.cycle_time_box.stop_timer()
                self.cycle_time_box.reset_timer()
                return
    
            self.test_file_path = full_path
            self.test_cases = self.parse_test_file(self.test_file_path)
            if not self.test_cases:
                self.instruction_box.append("No test cases found in the test file.")
                self.cycle_time_box.stop_timer()
                self.cycle_time_box.reset_timer()
                return
    
            self.load_tests_from_sku(battery_number, active_library)
    
            self.active_library_path = resource_path(active_library)
            if not os.path.isdir(self.active_library_path):
                self.instruction_box.append(f"Active library folder '{active_library}' not found.")
                self.cycle_time_box.stop_timer()
                self.cycle_time_box.reset_timer()
                return
    
            self.current_test_index = 0
            self.test_results = []
            self.test_times = []
            self.cumulative_time = 0.0
            self.start_time = time.time()
            self.final_status = "OK"
            self.run_next_test()
            return
    
        # === OLD FLOW for Diagnostics/TPMS ===
        if sku == "ERROR":
            selected_mode = self.api_selector.get_selected_api()
            mode_display = "Production (PRD)" if selected_mode == "PRD" else "Engineering Job Order (EJO)"
            self.instruction_box.setText(f'<span style="color:red;">Scanned VIN number is not in the Selected Mode: {mode_display}.</span>')
            self.vin_input.setText("")
            self.vin_input.clearFocus()
            self.vin_input.setFocus()
            self.cycle_time_box.stop_timer()
            self.cycle_time_box.reset_timer()
            return
    
        self.second_sub_box.set_value(sku)
        self.on_sku_changed(sku)
        print(f"[DEBUG] SKU fetched: {sku} | Library: {active_library}")
        self.sku = sku
        test_file = resource_path(os.path.join("sku_files", f"{sku} - Flashing - details.xlsx"))
        print(f"Test file path: {test_file}")
        if not os.path.exists(test_file):
            self.instruction_box.append(f"Test file for SKU '{sku}' not found.")
            self.cycle_time_box.stop_timer()
            self.cycle_time_box.reset_timer()
            return
    
        self.test_file_path = test_file
        if not active_library:
            self.instruction_box.append("Missing 'active_library' in station.ini")
            self.cycle_time_box.stop_timer()
            self.cycle_time_box.reset_timer()
            return
    
        self.active_library = active_library
        self.active_library_path = resource_path(active_library)
        if not os.path.isdir(self.active_library_path):
            self.instruction_box.append(f"Active library folder '{active_library}' not found.")
            self.cycle_time_box.stop_timer()
            self.cycle_time_box.reset_timer()
            return
    
        self.test_cases = self.parse_test_file(self.test_file_path)
        if not self.test_cases:
            self.instruction_box.append("No test cases found in the test file.")
            self.cycle_time_box.stop_timer()
            self.cycle_time_box.reset_timer()
            return
    
        self.current_test_index = 0
        self.test_results = []
        self.test_times = []
        self.cumulative_time = 0.0
        self.start_time = time.time()
        self.final_status = "OK"
        self.run_next_test()

    def start_test_cases(self):
        vin_number = self.vin_input.text().strip()
        self.instruction_box.setText('')
        active_library = self.active_library_selector.get_selected_library()
        if (
            (active_library == "3W_Battery_Healthcheck" and len(vin_number) != 12) or
            (active_library != "3W_Battery_Healthcheck" and (not vin_number.startswith("MD6") or len(vin_number) != 17))
        ):    
            self.instruction_box.append("Invalid identifier. Please scan a valid identifier.")
            self.vin_input.setText("")
            self.cycle_time_box.stop_timer()
            self.cycle_time_box.reset_timer()
            return
        api_url = self.api_selector.get_selected_api_url(vin_number)
        self.url = api_url
        self.cycle_start_time = datetime.now()
        self.cycle_time_box.start_timer()
        if active_library != "3W_Battery_Healthcheck":
            self.fetch_sku_from_api(vin_number, api_url)
        else:
            self.on_sku_fetched(vin_number[0])  # Just pass first digit

    def run_test(self, library_name, function_name, vin_number, api_url):
        self.test_thread = QThread()
        self.test_worker = TestWorker(library_name, function_name, vin_number, api_url)
        self.test_worker.moveToThread(self.test_thread)
    
        # Correct signal connections
        self.test_worker.result_ready.connect(lambda result, duration, logs: self._on_worker_result(result, duration, logs, self.current_test_index))
        self.test_worker.error_occurred.connect(lambda error, duration, logs: self._on_worker_error(error, duration, logs, self.current_test_index))
    
        self.test_thread.started.connect(self.test_worker.run)
        self.test_thread.finished.connect(self.test_worker.deleteLater)
        self.test_thread.finished.connect(self.test_thread.deleteLater)
    
        self.test_thread.start()

        
    def _on_worker_result(self, result, duration, logs, row):
        self.worker_thread.quit()
        self.worker_thread.wait()
    
        self.result = result
        self.test_duration = duration
        attempt_time = self.cycle_time_box.seconds
    
        # Ensure structure is list-based
        while len(self.test_results) <= self.current_test_index:
            self.test_results.append([])
            self.test_times.append([])
    
        if not isinstance(self.test_results[self.current_test_index], list):
            self.test_results[self.current_test_index] = list(self.test_results[self.current_test_index])
        if not isinstance(self.test_times[self.current_test_index], list):
            self.test_times[self.current_test_index] = list(self.test_times[self.current_test_index])
    
        self.test_results[self.current_test_index].append(logs)
        self.test_times[self.current_test_index].append(attempt_time)
    
        attempt_num = len(self.test_results[self.current_test_index])
        log_entry = (
            f"--- Retry {attempt_num} ---\n{logs.strip()}\nCycle Time (Retry {attempt_num}): {attempt_time:.2f} sec"
            if attempt_num > 1 else
            f"{logs.strip()}\nCycle Time: {attempt_time:.2f} sec"
        )
    
        self.append_to_log_file(log_entry)
        self._continue_after_worker(row)
    
    def _on_worker_error(self, error, duration, logs, row):
        self.worker_thread.quit()
        self.worker_thread.wait()
    
        self.result = error
        self.test_duration = duration
        attempt_time = self.cycle_time_box.seconds
    
        # Ensure structure is list-based
        while len(self.test_results) <= self.current_test_index:
            self.test_results.append([])
            self.test_times.append([])
    
        if not isinstance(self.test_results[self.current_test_index], list):
            self.test_results[self.current_test_index] = list(self.test_results[self.current_test_index])
        if not isinstance(self.test_times[self.current_test_index], list):
            self.test_times[self.current_test_index] = list(self.test_times[self.current_test_index])
    
        self.test_results[self.current_test_index].append(logs)
        self.test_times[self.current_test_index].append(attempt_time)  # ✅ fixed: no extra []
    
        attempt_num = len(self.test_results[self.current_test_index])
        log_entry = (
            f"--- Retry {attempt_num} ---\n{logs.strip()}\nCycle Time (Retry {attempt_num}): {attempt_time:.2f} sec"
            if attempt_num > 1 else
            f"{logs.strip()}\nCycle Time: {attempt_time:.2f} sec"
        )
        self.append_to_log_file(log_entry)
    
        self.instruction_box.clear()
        self.instruction_box.append(f"{self.test_cases[self.current_test_index][1]} failed due to: {error}")
    
        self.retry_count += 1
        if self.retry_count < self.max_retries:
            QTimer.singleShot(2000, lambda: self._start_worker(row, self.test_cases[self.current_test_index][1]))
        else:
            self.test_failed = True
            self.final_status = "NOK"
            self.update_test_result_row(row, "Timeout/Error", "FAILED")
            self.progress_bar.setValue(100)
            self.test_cycle_completed = True
            self.cycle_time_box.stop_timer()
            QTimer.singleShot(500, self.save_results_to_log)
            QTimer.singleShot(15000, lambda: self.reset_for_next_cycle())

    def run_next_test(self):
        if self.current_test_index < len(self.test_cases):
            test_label, function_name = self.test_cases[self.current_test_index]
            row = self.current_test_index
    
            self.retry_count = 0  # Reset retry count for this test
    
            if test_label.lower() == "flashing":  
                # Special handling for flashing step
                self.run_flashing_process(row)
            else:
                # Normal tests
                self._start_worker(row, function_name)
        else:
            # All tests done
            self.progress_bar.setValue(100)
            self.test_cycle_completed = True
            self.cycle_time_box.stop_timer()
            self.result_box.setText('<span style="color:green; font-weight:bold; font-size:24px;">All tests passed successfully!</span>')
            self.instruction_box.setText("System ready for next VIN number.")
            QTimer.singleShot(500, self.save_results_to_log)
            QTimer.singleShot(10000, lambda: self.reset_for_next_cycle())


    def _start_worker(self, row, function_name):
        active_library = self.active_library_selector.get_selected_library()
        vin_number = self.vin_input.text().strip()
        api_url = self.url
    
        self.worker_thread = QThread()
        self.worker = TestWorker(active_library, function_name, vin_number, api_url, self.append_to_log_file)
        self.worker.moveToThread(self.worker_thread)
    
        self.worker.result_ready.connect(lambda r, d, l: self._on_worker_result(r, d, l, row))
        self.worker.error_occurred.connect(lambda e, d, l: self._on_worker_error(e, d, l, row))
    
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.start()
        
    def _continue_after_worker(self, row):
        function_name = self.test_cases[self.current_test_index][1]
        test_name = self.test_table.item(row, 1).text()
        active_library = self.active_library_selector.get_selected_library()
    
        self.cumulative_time += self.test_duration
        self.test_times.append((function_name, self.cumulative_time))    
        expected_value = self.test_table.item(row, 3).text() if self.test_table.item(row, 3) else ""
        lsl = self.test_table.item(row, 4).text() if self.test_table.item(row, 4) else ""
        usl = self.test_table.item(row, 5).text() if self.test_table.item(row, 5) else ""    
        passed = False
        actual_value = ""
    
        try:
            result = self.result    
            # --- Full validation logic block ---
            if active_library == "3W_Diagnostics":
                if test_name in ["Battery_Version", "MCU_Version", "VCU_Version", "Cluster_Version", "Telematics_Version"]:
                    if isinstance(result, tuple) and len(result) == 2:
                        success, version = result
                        actual_value = version
                        passed = success and (version == expected_value)
                    else:
                        actual_value = "Error"
                elif test_name in ["Battery_SOC", "Battery_Voltage"]:
                    if isinstance(result, tuple) and len(result) == 2:
                        passed, actual_value = result
                        try:
                            val = float(actual_value)
                            lsl_val = float(lsl) if lsl and lsl != "N/A" else float('-inf')
                            usl_val = float(usl) if usl and usl != "N/A" else float('inf')
                            passed = passed and (lsl_val <= val <= usl_val)
                        except:
                            passed = False
                            actual_value = "Error"
                elif test_name in ["MCU_Vehicle_ID", "MCU_Phase_Offset"]:
                    if isinstance(result, tuple) and len(result) == 3:
                        passed, api_value, actual_value = result
                        self.test_table.setItem(row, 3, QTableWidgetItem(str(api_value)))
                    else:
                        actual_value = "Error"
                        passed = False
                elif isinstance(result, bool):
                    actual_value = "True" if result else "False"
                    passed = result
                elif isinstance(result, tuple):
                    success = result[0]
                    actual_value = str(result[1]) if len(result) > 1 else ""
                    passed = success and actual_value == expected_value
                else:
                    actual_value = str(result)
                    passed = bool(result)  
            elif active_library == "Flashing":
                if isinstance(result, bool):
                    actual_value = "True" if result else "False"
                    passed = result
                elif isinstance(result, tuple):
                    success = result[0]
                    actual_value = str(result[1]) if len(result) > 1 else ""
                    passed = success and actual_value == expected_value
                else:
                    actual_value = str(result)
                    passed = bool(result) 
            elif active_library == "3W_Battery_Healthcheck":
                if test_name in ["Battery_SOC", "Battery_Voltage", "Cell_Voltage_Imbalance", "Max_Cell_Temp", "Min_Cell_Temp"]:
                    if isinstance(result, tuple) and len(result) == 2:
                        passed, actual_value = result
                        try:
                            val = float(actual_value)
                            lsl_val = float(lsl) if lsl and lsl != "N/A" else float('-inf')
                            usl_val = float(usl) if usl and usl != "N/A" else float('inf')
                            passed = passed and (lsl_val <= val <= usl_val)
                        except:
                            actual_value = "Error"
                            passed = False
                elif test_name in ["Battery_Version"]:
                    if isinstance(result, tuple) and len(result) == 2:
                        success, version = result
                        actual_value = version
                        passed = success and (version == expected_value)
                    else:
                        actual_value = "Error"
                        passed = False
                else:
                    actual_value = str(result)
                    passed = bool(result)    
            else:  # TPMS
                if isinstance(result, tuple) and len(result) == 2:
                    passed, actual_value = result
                elif isinstance(result, bool):
                    actual_value = "True" if result else "False"
                    passed = result
                else:
                    actual_value = str(result)
                    passed = bool(result)    
        except Exception as e:
            print(f"[Error] Result parsing failed: {e}")
            actual_value = "Exception"
            passed = False    
        # Update GUI
        status = "PASSED" if passed else "FAILED"
        color = "#008000" if passed else "red"
        self.update_test_result_row(row, actual_value, status)
        self.result_box.setText(f'<span style="color:{color}; font-weight:bold; font-size:24px;">{function_name} - {status}</span>')
        self.test_table.scrollToItem(self.test_table.item(row, 0), QAbstractItemView.PositionAtCenter)
        self.progress_bar.setValue(int(((self.current_test_index + 1) / len(self.test_cases)) * 100))
    
        if passed:
            self.instruction_box.setText(f"{function_name} passed on attempt {self.retry_count + 1}")
            QTimer.singleShot(1000, self._proceed_to_next_test)
        else:
            self.retry_count += 1
            if self.retry_count < self.max_retries:
                self.instruction_box.setText(f"{function_name} failed on attempt {self.retry_count}. Retrying...")
                QTimer.singleShot(2000, lambda: self._start_worker(row, function_name))
            else:
                self.test_failed = True
                self.final_status = "NOK"
                self.instruction_box.setText(f"{function_name} failed after {self.max_retries} retries.")
                self.progress_bar.setValue(100)
                self.test_cycle_completed = True
                self.cycle_time_box.stop_timer()
                QTimer.singleShot(500, self.save_results_to_log)
                QTimer.singleShot(15000, lambda: self.reset_for_next_cycle())

    def _proceed_to_next_test(self):
        try:
            if hasattr(self, 'test_failed') and self.test_failed:
                return
            self.current_test_index += 1
            self.run_next_test()
        except Exception as e:
            print(f"[Error] Proceed to next test failed: {e}")
            self.instruction_box.append(f'<span style="color:red;">Exception in _proceed_to_next_test: {e}</span>')

    def send_api_status(self):
        vin_number = self.vin_input.text().strip()
        active_library = self.active_library_selector.get_selected_library()
        self.API_URL = "http://10.121.2.107:3000/vehicles/processParams/updateProcessParams"

        if not vin_number:
            print("VIN number is empty. Cannot send API status.")
            return

        headers = {'Content-Type': 'application/json'}
        payload = {
            "VIN": vin_number,
            "paramId": "CZ14001" if active_library == "Flashing" else "CZ14104",
            "opnNo": "0010" if active_library == "Flashing" else "0022",
            "identifier": vin_number,
            "result": self.final_status
        }
        try:
            print("Sending final result to API...")
            print("Request URL:", self.API_URL)
            print("Payload:", json.dumps(payload, indent=4))
            response = requests.post(self.API_URL, headers=headers, data=json.dumps(payload))
            print(f"API Response [{response.status_code}]: {response.text}")
        except Exception as e:
            print(f"Failed to send final result to API: {e}")

    def save_results_to_log(self):
        vin_number = self.vin_input.text().strip()
        timestamp_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_cycle_time = getattr(self, 'cycle_start_time', 'N/A').strftime("%Y-%m-%d %H:%M:%S") if hasattr(self, 'cycle_start_time') else 'N/A'
        total_cycle_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        url = getattr(self, 'url', 'No request sent')
        json_response = getattr(self, 'json_response', 'No response available')

        log_folder = r"D:\Python\TVS NIRIX Flashing\test_results"
        os.makedirs(log_folder, exist_ok=True)

        txt_filename = f"{vin_number}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.txt"
        txt_path = os.path.join(log_folder, txt_filename)

        try:
            with open(txt_path, 'a', encoding='utf-8') as file:
                file.write(f"Identifier Number      : {vin_number}\n")
                file.write(f"TEST STATUS     : {self.final_status}\n")
                file.write(f"DATE            : {timestamp_now}\n")
                file.write("API Request:\n")
                file.write(f"{url}\n")
                file.write("API Response:\n")
                file.write('\n')
                if isinstance(json_response, dict):
                    file.write(json.dumps(json_response, indent=4))
                else:
                    file.write(str(json_response))
                # Loop through each test and its attempts
                for idx, attempts in enumerate(self.test_results):
                    for attempt_num, log_text in enumerate(attempts, start=1):
                        if attempt_num > 1:
                            file.write(f"--- Retry {attempt_num} ---\n")
                        file.write(log_text.strip() + "\n")
                        retry_time = self.test_times[idx][attempt_num - 1]
                        #file.write(f"Cycle Time: {self.test_times[idx][1]:.2f} sec\n\n")
                        file.write(f"Cycle Time (Retry {attempt_num}): {retry_time:.2f} sec\n\n")
    
                file.write(f"START CYCLE TIME: {start_cycle_time}\n")
                file.write(f"TOTAL CYCLE TIME: {total_cycle_time}\n")
    
            print(f"Results appended to: {txt_path}")
        except Exception as e:
            print(f"Error saving log file: {e}")
            self.instruction_box.append(str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    light_palette = QPalette()
    light_palette.setColor(QPalette.Window, QColor(255, 255, 255))
    light_palette.setColor(QPalette.WindowText, Qt.black)
    light_palette.setColor(QPalette.Base, QColor(240, 240, 240))
    light_palette.setColor(QPalette.AlternateBase, QColor(230, 230, 230))
    light_palette.setColor(QPalette.ToolTipBase, Qt.black)
    light_palette.setColor(QPalette.ToolTipText, Qt.black)
    light_palette.setColor(QPalette.Text, Qt.black)
    light_palette.setColor(QPalette.Button, QColor(230, 230, 230))
    light_palette.setColor(QPalette.ButtonText, Qt.black)
    light_palette.setColor(QPalette.BrightText, Qt.red)
    light_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    light_palette.setColor(QPalette.HighlightedText, Qt.black)
    app.setPalette(light_palette)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
