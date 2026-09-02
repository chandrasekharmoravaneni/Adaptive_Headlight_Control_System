import sys
import re
import time
import os
import csv

from datetime import datetime
from collections import deque

import serial
import pyqtgraph as pg

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QPushButton,
    QFileDialog
)


# ============================================================
# STM32 UART CONFIGURATION
# ============================================================

SERIAL_PORT = "/dev/cu.usbmodem11303"
BAUD_RATE = 115200

# Number of samples visible in live graph
MAX_POINTS = 300

# Real-time graph window
GRAPH_WINDOW_SECONDS = 15.0

# UART timeout
TELEMETRY_TIMEOUT_S = 2.0


# ============================================================
# PWM DIRECTION DIAGNOSTIC
# ============================================================

# Minimum target PWM change considered a meaningful step
PWM_STEP_THRESHOLD = 10

# Number of consecutive wrong-direction samples
# before declaring FAULT
PWM_FAULT_COUNT = 10

# PWM error allowed for recovery
PWM_RECOVERY_ERROR = 50

# Normal tracking tolerance
PWM_OK_ERROR = 25


# ============================================================
# LIGHTING STATES
# ============================================================

NIGHT = 0
CLOUDY = 1
DAYLIGHT = 2
FAULT = 3


# ============================================================
# DASHBOARD
# ============================================================

class HeadlightDashboard(QWidget):

    def __init__(self):

        super().__init__()

        # ----------------------------------------------------
        # WINDOW
        # ----------------------------------------------------

        self.setWindowTitle(
            "STM32 Automatic Headlight Monitor"
        )

        self.resize(
            1450,
            1050
        )


        # ====================================================
        # MONITORING CONTROL
        # ====================================================

        # IMPORTANT:
        # Dashboard starts STOPPED.
        # User must press START MONITORING.

        self.monitoring = False
        self.receiving_data = False

        self.sample_number = 0

        self.start_time = None
        self.last_packet_time = None
        self.last_sample_time = None

        self.rate_samples = deque(
            maxlen=20
        )

        self.maximum_packet_gap = 0.0

        self.current_state = None
        self.state_start_time = None


        # ----------------------------------------------------
        # Previous PWM values
        # ----------------------------------------------------

        self.last_target_pwm = None
        self.last_actual_pwm = None


        # ----------------------------------------------------
        # PWM diagnostic
        # ----------------------------------------------------

        self.pwm_fault_counter = 0
        self.pwm_fault_active = False


        # ====================================================
        # EVENT / FAULT HISTORY
        # ====================================================

        self.event_log = deque(
            maxlen=200
        )

        self.last_event_text = "NO EVENTS"


        # ====================================================
        # SERIAL CONNECTION
        # ====================================================

        self.ser = None
        self.serial_connected = False

        try:

            self.ser = serial.Serial(
                SERIAL_PORT,
                BAUD_RATE,
                timeout=0.01
            )

            self.serial_connected = True

            print(
                f"Connected to {SERIAL_PORT}"
            )

        except Exception as e:

            print(
                f"Serial connection failed: {e}"
            )


        # ====================================================
        # TELEMETRY LOGGER
        # ====================================================

        self.log_file = None
        self.log_writer = None
        self.log_file_path = None

        self.event_file = None
        self.event_writer = None
        self.event_file_path = None

        self.summary_file = None
        self.summary_writer = None
        self.summary_file_path = None


        # ----------------------------------------------------
        # Log directory
        # ----------------------------------------------------

        self.log_directory = os.path.join(
            os.path.expanduser("~"),
            "stm32_dashboard",
            "telemetry_logs"
        )

        os.makedirs(
            self.log_directory,
            exist_ok=True
        )


        # ====================================================
        # MONITORING SESSION
        # ====================================================

        self.session_id = None

        self.session_start_timestamp = None

        self.session_stop_timestamp = None

        self.session_sample_count = 0


        # ====================================================
        # DATA BUFFERS
        # ====================================================

        self.time_data = deque(
            maxlen=MAX_POINTS
        )

        self.raw_lux_data = deque(
            maxlen=MAX_POINTS
        )

        self.filtered_lux_data = deque(
            maxlen=MAX_POINTS
        )

        self.target_pwm_data = deque(
            maxlen=MAX_POINTS
        )

        self.actual_pwm_data = deque(
            maxlen=MAX_POINTS
        )

        self.condition_data = deque(
            maxlen=MAX_POINTS
        )


        # ====================================================
        # BUILD UI
        # ====================================================

        self.setup_ui()


        # ====================================================
        # UART POLLING
        # ====================================================

        self.timer = QTimer()

        self.timer.timeout.connect(
            self.read_serial
        )

        self.timer.start(20)


        # ====================================================
        # STATUS TIMER
        # ====================================================

        self.status_timer = QTimer()

        self.status_timer.timeout.connect(
            self.update_status
        )

        self.status_timer.start(250)


    # ========================================================
    # USER INTERFACE
    # ========================================================

    def setup_ui(self):

        main_layout = QVBoxLayout()

        main_layout.setSpacing(4)

        main_layout.setContentsMargins(
            5,
            5,
            5,
            5
        )


        # ====================================================
        # TITLE
        # ====================================================

        title = QLabel(
            "STM32 AUTOMATIC HEADLIGHT MONITOR"
        )

        title.setStyleSheet(
            """
            QLabel {
                font-size: 24px;
                font-weight: bold;
                padding: 2px;
            }
            """
        )

        main_layout.addWidget(
            title
        )


        # ====================================================
        # CONTROL BUTTONS
        # ====================================================

        control_layout = QHBoxLayout()

        control_layout.setSpacing(8)


        self.start_button = QPushButton(
            "START MONITORING"
        )

        self.stop_button = QPushButton(
            "STOP MONITORING"
        )

        self.save_button = QPushButton(
            "EXPORT GRAPHS"
        )


        self.start_button.clicked.connect(
            self.start_monitoring
        )

        self.stop_button.clicked.connect(
            self.stop_monitoring
        )

        self.save_button.clicked.connect(
            self.save_graphs
        )


        control_layout.addWidget(
            self.start_button
        )

        control_layout.addWidget(
            self.stop_button
        )

        control_layout.addWidget(
            self.save_button
        )

        control_layout.addStretch()


        main_layout.addLayout(
            control_layout
        )


        # ====================================================
        # SYSTEM STATUS
        # ====================================================

        status_box = QGroupBox(
            "System Status"
        )

        status_layout = QGridLayout()

        status_layout.setHorizontalSpacing(
            25
        )

        status_layout.setVerticalSpacing(
            2
        )


        self.stm32_status_label = QLabel(
            "STM32: CONNECTING..."
        )

        self.uart_status_label = QLabel(
            "UART: WAITING"
        )

        self.telemetry_status_label = QLabel(
            "TELEMETRY: WAITING"
        )

        self.monitor_status_label = QLabel(
            "MONITOR: STOPPED"
        )


        self.rate_label = QLabel(
            "RATE: 0.00 Hz"
        )

        self.sample_label = QLabel(
            "SAMPLES: 0"
        )

        self.packet_gap_label = QLabel(
            "MAX GAP: 0 ms"
        )

        self.state_duration_label = QLabel(
            "STATE TIME: --"
        )


        status_layout.addWidget(
            self.stm32_status_label,
            0,
            0
        )

        status_layout.addWidget(
            self.uart_status_label,
            0,
            1
        )

        status_layout.addWidget(
            self.telemetry_status_label,
            0,
            2
        )

        status_layout.addWidget(
            self.monitor_status_label,
            0,
            3
        )


        status_layout.addWidget(
            self.rate_label,
            1,
            0
        )

        status_layout.addWidget(
            self.sample_label,
            1,
            1
        )

        status_layout.addWidget(
            self.packet_gap_label,
            1,
            2
        )

        status_layout.addWidget(
            self.state_duration_label,
            1,
            3
        )


        self.last_packet_label = QLabel(
            "LAST PACKET: --"
        )

        self.event_label = QLabel(
            "EVENT: NO EVENTS"
        )


        status_layout.addWidget(
            self.last_packet_label,
            2,
            0,
            1,
            2
        )

        status_layout.addWidget(
            self.event_label,
            2,
            2,
            1,
            2
        )


        status_box.setLayout(
            status_layout
        )

        main_layout.addWidget(
            status_box
        )


        # ====================================================
        # LIVE CONTROLLER DATA
        # ====================================================

        values_box = QGroupBox(
            "Live Sensor / Controller Data"
        )

        values_layout = QGridLayout()

        values_layout.setHorizontalSpacing(
            35
        )

        values_layout.setVerticalSpacing(
            3
        )


        self.raw_lux_label = QLabel(
            "0 lux"
        )

        self.filtered_lux_label = QLabel(
            "0 lux"
        )

        self.stable_lux_label = QLabel(
            "0 lux"
        )

        self.target_pwm_label = QLabel(
            "0"
        )

        self.actual_pwm_label = QLabel(
            "0"
        )

        self.pwm_difference_label = QLabel(
            "0"
        )

        self.pwm_tracking_label = QLabel(
            "0.0 %"
        )

        self.pwm_status_label = QLabel(
            "UNKNOWN"
        )

        self.state_label = QLabel(
            "UNKNOWN"
        )


        value_style = """
            QLabel {
                font-size: 16px;
                font-weight: bold;
            }
        """


        for label in (
            self.raw_lux_label,
            self.filtered_lux_label,
            self.stable_lux_label,
            self.target_pwm_label,
            self.actual_pwm_label,
            self.pwm_difference_label,
            self.pwm_tracking_label,
            self.pwm_status_label,
            self.state_label
        ):

            label.setStyleSheet(
                value_style
            )


        # ----------------------------------------------------
        # Row 1
        # ----------------------------------------------------

        values_layout.addWidget(
            QLabel("Raw Lux:"),
            0,
            0
        )

        values_layout.addWidget(
            self.raw_lux_label,
            0,
            1
        )

        values_layout.addWidget(
            QLabel("Filtered Lux:"),
            0,
            2
        )

        values_layout.addWidget(
            self.filtered_lux_label,
            0,
            3
        )


        # ----------------------------------------------------
        # Row 2
        # ----------------------------------------------------

        values_layout.addWidget(
            QLabel("Stable Lux:"),
            1,
            0
        )

        values_layout.addWidget(
            self.stable_lux_label,
            1,
            1
        )

        values_layout.addWidget(
            QLabel("Target PWM:"),
            1,
            2
        )

        values_layout.addWidget(
            self.target_pwm_label,
            1,
            3
        )


        # ----------------------------------------------------
        # Row 3
        # ----------------------------------------------------

        values_layout.addWidget(
            QLabel("Actual PWM:"),
            2,
            0
        )

        values_layout.addWidget(
            self.actual_pwm_label,
            2,
            1
        )

        values_layout.addWidget(
            QLabel("PWM Error:"),
            2,
            2
        )

        values_layout.addWidget(
            self.pwm_difference_label,
            2,
            3
        )


        # ----------------------------------------------------
        # Row 4
        # ----------------------------------------------------

        values_layout.addWidget(
            QLabel("PWM Tracking:"),
            3,
            0
        )

        values_layout.addWidget(
            self.pwm_tracking_label,
            3,
            1
        )

        values_layout.addWidget(
            QLabel("PWM Status:"),
            3,
            2
        )

        values_layout.addWidget(
            self.pwm_status_label,
            3,
            3
        )


        # ----------------------------------------------------
        # Row 5
        # ----------------------------------------------------

        values_layout.addWidget(
            QLabel("Headlight State:"),
            4,
            0
        )

        values_layout.addWidget(
            self.state_label,
            4,
            1,
            1,
            3
        )


        values_box.setLayout(
            values_layout
        )

        main_layout.addWidget(
            values_box
        )


        # ====================================================
        # GRAPH 1 - RAW LUX
        # ====================================================

        self.raw_plot = pg.PlotWidget()

        self.raw_plot.setTitle(
            "Real-Time Raw Ambient Light"
        )

        self.raw_plot.setLabel(
            "left",
            "Raw Lux"
        )

        self.raw_plot.setLabel(
            "bottom",
            "Time",
            units="s"
        )

        self.raw_plot.showGrid(
            x=True,
            y=True,
            alpha=0.3
        )

        self.raw_plot.setMinimumHeight(
            180
        )

        self.raw_curve = self.raw_plot.plot(
            pen=pg.mkPen(
                color="w",
                width=2
            )
        )


        # ====================================================
        # GRAPH 2 - FILTERED LUX
        # ====================================================

        self.filtered_plot = pg.PlotWidget()

        self.filtered_plot.setTitle(
            "Real-Time Filtered Lux"
        )

        self.filtered_plot.setLabel(
            "left",
            "Filtered Lux"
        )

        self.filtered_plot.setLabel(
            "bottom",
            "Time",
            units="s"
        )

        self.filtered_plot.showGrid(
            x=True,
            y=True,
            alpha=0.3
        )

        self.filtered_plot.setMinimumHeight(
            180
        )

        self.filtered_curve = self.filtered_plot.plot(
            pen=pg.mkPen(
                color="w",
                width=2
            )
        )


        # ====================================================
        # GRAPH 3 - TARGET + ACTUAL PWM
        # ====================================================

        self.pwm_plot = pg.PlotWidget()

        self.pwm_plot.setTitle(
            "Real-Time Headlight PWM"
        )

        self.pwm_plot.setLabel(
            "left",
            "PWM"
        )

        self.pwm_plot.setLabel(
            "bottom",
            "Time",
            units="s"
        )

        self.pwm_plot.setYRange(
            0,
            1000,
            padding=0
        )

        self.pwm_plot.showGrid(
            x=True,
            y=True,
            alpha=0.3
        )

        self.pwm_plot.setMinimumHeight(
            180
        )


        target_pen = pg.mkPen(
            color="r",
            width=2,
            style=Qt.PenStyle.DashLine
        )

        self.target_pwm_curve = (
            self.pwm_plot.plot(
                pen=target_pen,
                name="Target PWM"
            )
        )


        actual_pen = pg.mkPen(
            color="g",
            width=3
        )

        self.actual_pwm_curve = (
            self.pwm_plot.plot(
                pen=actual_pen,
                name="Actual PWM"
            )
        )


        self.pwm_plot.addLegend(
            offset=(10, 10)
        )


        # ====================================================
        # GRAPH 4 - LIGHTING STATE
        # ====================================================

        self.state_plot = pg.PlotWidget()

        self.state_plot.setTitle(
            "Real-Time Lighting Condition"
        )

        self.state_plot.setLabel(
            "left",
            "Condition"
        )

        self.state_plot.setLabel(
            "bottom",
            "Time",
            units="s"
        )

        self.state_plot.setYRange(
            -0.2,
            3.2,
            padding=0
        )

        self.state_plot.showGrid(
            x=True,
            y=True,
            alpha=0.3
        )

        self.state_plot.setMinimumHeight(
            180
        )


        state_axis = (
            self.state_plot.getAxis(
                "left"
            )
        )

        state_axis.setTicks(
            [
                [
                    (
                        NIGHT,
                        "Night"
                    ),
                    (
                        CLOUDY,
                        "Cloudy / Rainy"
                    ),
                    (
                        DAYLIGHT,
                        "Daylight"
                    ),
                    (
                        FAULT,
                        "FAULT"
                    )
                ]
            ]
        )


        self.state_curve = (
            self.state_plot.plot(
                pen=pg.mkPen(
                    color="w",
                    width=2
                ),
                symbol="o",
                symbolSize=4
            )
        )


        # ====================================================
        # GRAPH GRID - 2 x 2
        # ====================================================

        graph_grid = QGridLayout()

        graph_grid.setHorizontalSpacing(
            8
        )

        graph_grid.setVerticalSpacing(
            8
        )


        graph_grid.addWidget(
            self.raw_plot,
            0,
            0
        )

        graph_grid.addWidget(
            self.filtered_plot,
            0,
            1
        )

        graph_grid.addWidget(
            self.pwm_plot,
            1,
            0
        )

        graph_grid.addWidget(
            self.state_plot,
            1,
            1
        )


        graph_grid.setColumnStretch(
            0,
            1
        )

        graph_grid.setColumnStretch(
            1,
            1
        )

        graph_grid.setRowStretch(
            0,
            1
        )

        graph_grid.setRowStretch(
            1,
            1
        )


        main_layout.addLayout(
            graph_grid
        )


        # ====================================================
        # FINAL WINDOW
        # ====================================================

        self.setLayout(
            main_layout
        )


    # ========================================================
    # START TELEMETRY LOG
    # ========================================================

    def start_telemetry_log(self):

        # Prevent duplicate logger
        if self.log_file is not None:
            return


        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )


        self.session_id = timestamp


        self.session_start_timestamp = (
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )[:-3]
        )


        self.session_stop_timestamp = None

        self.session_sample_count = 0


        # ====================================================
        # FILE PATHS
        # ====================================================

        self.log_file_path = os.path.join(
            self.log_directory,
            f"headlight_telemetry_{timestamp}.csv"
        )

        self.event_file_path = os.path.join(
            self.log_directory,
            f"headlight_events_{timestamp}.csv"
        )

        self.summary_file_path = os.path.join(
            self.log_directory,
            f"headlight_session_{timestamp}.csv"
        )


        try:

            # =================================================
            # TELEMETRY CSV
            # =================================================

            self.log_file = open(
                self.log_file_path,
                "w",
                newline="",
                encoding="utf-8"
            )


            self.log_writer = csv.writer(
                self.log_file
            )


            self.log_writer.writerow(
                [
                    "Session_ID",
                    "Timestamp",
                    "Elapsed_s",
                    "Sample",
                    "Raw_Lux",
                    "Filtered_Lux",
                    "Stable_Lux",
                    "Target_PWM",
                    "Actual_PWM",
                    "PWM_Error",
                    "PWM_Tracking_Percent",
                    "PWM_Status",
                    "State"
                ]
            )


            self.log_file.flush()


            # =================================================
            # EVENT CSV
            # =================================================

            self.event_file = open(
                self.event_file_path,
                "w",
                newline="",
                encoding="utf-8"
            )


            self.event_writer = csv.writer(
                self.event_file
            )


            self.event_writer.writerow(
                [
                    "Session_ID",
                    "Timestamp",
                    "Elapsed_s",
                    "Event",
                    "Severity"
                ]
            )


            self.event_file.flush()


            print("")
            print("========================================")
            print("NEW MONITORING SESSION")
            print("========================================")
            print(
                f"Session ID : {self.session_id}"
            )
            print(
                f"Telemetry  : {self.log_file_path}"
            )
            print(
                f"Events     : {self.event_file_path}"
            )
            print(
                f"Summary    : {self.summary_file_path}"
            )
            print("========================================")
            print("")


        except Exception as e:

            print(
                f"Logging error: {e}"
            )

            self.close_log_files()


    # ========================================================
    # CLOSE LOG FILES
    # ========================================================

    def close_log_files(self):

        # ----------------------------------------------------
        # Telemetry
        # ----------------------------------------------------

        if self.log_file is not None:

            try:

                self.log_file.flush()
                self.log_file.close()

            except Exception as e:

                print(
                    f"Telemetry close error: {e}"
                )


        # ----------------------------------------------------
        # Events
        # ----------------------------------------------------

        if self.event_file is not None:

            try:

                self.event_file.flush()
                self.event_file.close()

            except Exception as e:

                print(
                    f"Event close error: {e}"
                )


        self.log_file = None
        self.log_writer = None

        self.event_file = None
        self.event_writer = None


    # ========================================================
    # ADD EVENT
    # ========================================================

    def add_event(
        self,
        event_text,
        severity="INFO"
    ):

        elapsed_time = 0.0


        if self.start_time is not None:

            elapsed_time = (
                time.monotonic()
                - self.start_time
            )


        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]


        event = (
            timestamp,
            elapsed_time,
            event_text,
            severity
        )


        # ----------------------------------------------------
        # Keep event in memory
        # ----------------------------------------------------

        self.event_log.append(
            event
        )


        self.last_event_text = (
            f"{severity}: {event_text}"
        )


        self.event_label.setText(
            f"EVENT: {self.last_event_text}"
        )


        # ----------------------------------------------------
        # Save event to current session
        # ----------------------------------------------------

        if self.event_writer is not None:

            try:

                self.event_writer.writerow(
                    [
                        self.session_id,
                        timestamp,
                        f"{elapsed_time:.3f}",
                        event_text,
                        severity
                    ]
                )


                self.event_file.flush()


            except Exception as e:

                print(
                    f"Event logging error: {e}"
                )


        print(
            f"[{severity}] {event_text}"
        )


    # ========================================================
    # CALCULATE PWM METRICS
    # ========================================================

    def calculate_pwm_metrics(
        self,
        target_pwm,
        actual_pwm
    ):

        # ====================================================
        # PWM ERROR
        # ====================================================

        pwm_error = (
            target_pwm
            - actual_pwm
        )


        # ====================================================
        # PWM TRACKING
        # ====================================================

        if target_pwm == 0:

            if actual_pwm == 0:

                tracking = 100.0

            else:

                tracking = 0.0

        else:

            tracking = (
                100.0
                * (
                    1.0
                    - (
                        abs(pwm_error)
                        / float(target_pwm)
                    )
                )
            )


            tracking = max(
                0.0,
                min(
                    100.0,
                    tracking
                )
            )


        # ====================================================
        # FIRST SAMPLE
        # ====================================================

        if (
            self.last_target_pwm is None
            or self.last_actual_pwm is None
        ):

            self.last_target_pwm = target_pwm

            self.last_actual_pwm = actual_pwm

            self.pwm_fault_counter = 0

            self.pwm_fault_active = False


            return (
                pwm_error,
                tracking,
                "OK"
            )


        # ====================================================
        # DETERMINE CHANGES
        # ====================================================

        target_change = (
            target_pwm
            - self.last_target_pwm
        )


        actual_change = (
            actual_pwm
            - self.last_actual_pwm
        )


        # ====================================================
        # TARGET DIRECTION
        # ====================================================

        target_direction = 0


        if target_change >= PWM_STEP_THRESHOLD:

            # Target increased
            target_direction = 1


        elif target_change <= -PWM_STEP_THRESHOLD:

            # Target decreased
            target_direction = -1


        # ====================================================
        # ACTUAL DIRECTION
        # ====================================================

        actual_direction = 0


        if actual_change >= PWM_STEP_THRESHOLD:

            actual_direction = 1


        elif actual_change <= -PWM_STEP_THRESHOLD:

            actual_direction = -1


        # ====================================================
        # DIRECTION CHECK
        # ====================================================

        wrong_direction = False

        no_movement = False


        if target_direction != 0:

            # ------------------------------------------------
            # Target increased
            # Actual should increase
            # ------------------------------------------------
           

            if target_direction == 1:

                if actual_direction == -1:

                    wrong_direction = True

                elif actual_direction == 0:

                    no_movement = True


            # ------------------------------------------------
            # Target decreased
            # Actual should decrease
            # ------------------------------------------------

            elif target_direction == -1:

                if actual_direction == 1:

                    wrong_direction = True

                elif actual_direction == 0:

                    no_movement = True


        # ====================================================
        # PERSISTENT WRONG DIRECTION
        # ====================================================

        if wrong_direction:

            self.pwm_fault_counter += 1

        else:

            self.pwm_fault_counter = 0


        # ====================================================
        # PERSISTENT FAULT
        # ====================================================

        if (
            self.pwm_fault_counter
            >= PWM_FAULT_COUNT
        ):

            if not self.pwm_fault_active:

                self.pwm_fault_active = True

                self.add_event(
                    "PWM actual value moving in wrong direction",
                    "FAULT"
                )


            pwm_status = "FAULT"


        # ====================================================
        # RECOVERY
        # ====================================================

        elif self.pwm_fault_active:

            if (
                not wrong_direction
                and abs(pwm_error)
                <= PWM_RECOVERY_ERROR
            ):

                self.pwm_fault_active = False

                self.pwm_fault_counter = 0


                self.add_event(
                    "PWM direction and tracking recovered",
                    "OK"
                )


                pwm_status = "OK"


            else:

                pwm_status = "FAULT"


        # ====================================================
        # NORMAL OPERATION
        # ====================================================

        elif wrong_direction:

            pwm_status = "WARNING"


        elif no_movement:

            pwm_status = "WARNING"


        elif abs(pwm_error) <= PWM_OK_ERROR:

            pwm_status = "OK"


        else:

            pwm_status = "TRACKING"


        # ====================================================
        # SAVE CURRENT VALUES
        # ====================================================

        self.last_target_pwm = target_pwm

        self.last_actual_pwm = actual_pwm


        return (
            pwm_error,
            tracking,
            pwm_status
        )


    # ========================================================
    # LOG ONE TELEMETRY SAMPLE
    # ========================================================

    def log_telemetry(
        self,
        lux,
        filtered,
        stable,
        state,
        target_pwm,
        actual_pwm,
        elapsed_time,
        pwm_error,
        pwm_tracking,
        pwm_status
    ):

        if (
            self.log_file is None
            or self.log_writer is None
        ):

            return


        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]


        self.log_writer.writerow(
            [
                self.session_id,
                timestamp,
                f"{elapsed_time:.3f}",
                self.sample_number,
                lux,
                filtered,
                stable,
                target_pwm,
                actual_pwm,
                pwm_error,
                f"{pwm_tracking:.2f}",
                pwm_status,
                state
            ]
        )


        # ----------------------------------------------------
        # Flush every sample
        # ----------------------------------------------------

        self.log_file.flush()


        self.session_sample_count += 1


    # ========================================================
    # START MONITORING
    # ========================================================

    def start_monitoring(self):

        # ----------------------------------------------------
        # Prevent duplicate START
        # ----------------------------------------------------

        if self.monitoring:

            return


        # ====================================================
        # CLOSE ANY OLD LOGGER
        # ====================================================

        self.close_log_files()


        # ====================================================
        # NEW SESSION
        # ====================================================

        self.monitoring = True

        self.receiving_data = False

        self.sample_number = 0

        self.start_time = time.monotonic()

        self.last_packet_time = None

        self.last_sample_time = None

        self.rate_samples.clear()

        self.maximum_packet_gap = 0.0

        self.current_state = None

        self.state_start_time = None


        # ----------------------------------------------------
        # Reset PWM diagnostic
        # ----------------------------------------------------

        self.last_target_pwm = None

        self.last_actual_pwm = None

        self.pwm_fault_counter = 0

        self.pwm_fault_active = False


        # ====================================================
        # CLEAR OLD EVENTS
        # ====================================================

        self.event_log.clear()

        self.last_event_text = "NO EVENTS"


        # ====================================================
        # CLEAR LIVE GRAPH BUFFERS
        # ====================================================

        self.time_data.clear()

        self.raw_lux_data.clear()

        self.filtered_lux_data.clear()

        self.target_pwm_data.clear()

        self.actual_pwm_data.clear()

        self.condition_data.clear()


        # ====================================================
        # CLEAR GRAPH CURVES
        # ====================================================

        self.raw_curve.clear()

        self.filtered_curve.clear()

        self.target_pwm_curve.clear()

        self.actual_pwm_curve.clear()

        self.state_curve.clear()


        # ====================================================
        # RESET GRAPH AXES
        # ====================================================

        self.raw_plot.setXRange(
            0,
            1,
            padding=0
        )

        self.filtered_plot.setXRange(
            0,
            1,
            padding=0
        )

        self.pwm_plot.setXRange(
            0,
            1,
            padding=0
        )

        self.state_plot.setXRange(
            0,
            1,
            padding=0
        )


        # ====================================================
        # RESET UI
        # ====================================================

        self.monitor_status_label.setText(
            "MONITOR: WAITING FOR STM32"
        )

        self.telemetry_status_label.setText(
            "TELEMETRY: WAITING"
        )

        self.rate_label.setText(
            "RATE: 0.00 Hz"
        )

        self.sample_label.setText(
            "SAMPLES: 0"
        )

        self.packet_gap_label.setText(
            "MAX GAP: 0 ms"
        )

        self.state_duration_label.setText(
            "STATE TIME: --"
        )

        self.last_packet_label.setText(
            "LAST PACKET: --"
        )

        self.event_label.setText(
            "EVENT: MONITORING STARTED"
        )


        self.raw_lux_label.setText(
            "0 lux"
        )

        self.filtered_lux_label.setText(
            "0 lux"
        )

        self.stable_lux_label.setText(
            "0 lux"
        )

        self.target_pwm_label.setText(
            "0"
        )

        self.actual_pwm_label.setText(
            "0"
        )

        self.pwm_difference_label.setText(
            "0"
        )

        self.pwm_tracking_label.setText(
            "0.0 %"
        )

        self.pwm_status_label.setText(
            "UNKNOWN"
        )

        self.state_label.setText(
            "UNKNOWN"
        )


        # ====================================================
        # CREATE NEW SESSION LOG
        #
        # IMPORTANT:
        # This happens immediately after START.
        # ====================================================

        self.start_telemetry_log()


        # ====================================================
        # RECORD START EVENT
        # ====================================================

        self.add_event(
            "Monitoring session started",
            "INFO"
        )


        print(
            "Monitoring started."
        )


    # ========================================================
    # STOP MONITORING
    # ========================================================

    def stop_monitoring(self):

        # ----------------------------------------------------
        # Ignore if already stopped
        # ----------------------------------------------------

        if not self.monitoring:

            return


        # ====================================================
        # STOP ACCEPTING TELEMETRY
        # ====================================================

        self.monitoring = False


        # ====================================================
        # FINAL STOP TIMESTAMP
        # ====================================================

        self.session_stop_timestamp = (
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )[:-3]
        )


        # ====================================================
        # FINAL STOP EVENT
        # ====================================================

        self.add_event(
            "Monitoring session stopped",
            "INFO"
        )


        # ====================================================
        # SESSION DURATION
        # ====================================================

        duration = 0.0


        if self.start_time is not None:

            duration = (
                time.monotonic()
                - self.start_time
            )


        # ====================================================
        # SAVE SESSION SUMMARY
        # ====================================================

        self.save_session_summary(
            duration
        )


        # ====================================================
        # STORE PATHS BEFORE CLOSING
        # ====================================================

        telemetry_path = (
            self.log_file_path
        )

        event_path = (
            self.event_file_path
        )

        summary_path = (
            self.summary_file_path
        )

        samples = (
            self.session_sample_count
        )


        # ====================================================
        # FLUSH + CLOSE
        # ====================================================

        self.close_log_files()


        # ====================================================
        # UPDATE UI
        # ====================================================

        self.monitor_status_label.setText(
            "MONITOR: STOPPED"
        )

        self.telemetry_status_label.setText(
            "TELEMETRY: SESSION SAVED"
        )

        self.event_label.setText(
            "EVENT: INFO: Monitoring session stopped"
        )


        # ====================================================
        # IMPORTANT
        #
        # DO NOT CLEAR GRAPH DATA.
        #
        # The complete visible live graph remains.
        # ====================================================

        print("")
        print("========================================")
        print("MONITORING SESSION COMPLETE")
        print("========================================")
        print(
            f"Session ID      : {self.session_id}"
        )
        print(
            f"Duration        : {duration:.3f} s"
        )
        print(
            f"Samples         : {samples}"
        )
        print(
            f"Telemetry log   : {telemetry_path}"
        )
        print(
            f"Event log       : {event_path}"
        )
        print(
            f"Session summary : {summary_path}"
        )
        print("========================================")
        print("")


    # ========================================================
    # SAVE SESSION SUMMARY
    # ========================================================

    def save_session_summary(
        self,
        duration
    ):

        if self.summary_file_path is None:

            return


        try:

            with open(
                self.summary_file_path,
                "w",
                newline="",
                encoding="utf-8"
            ) as summary_file:

                writer = csv.writer(
                    summary_file
                )


                writer.writerow(
                    [
                        "Parameter",
                        "Value"
                    ]
                )


                writer.writerow(
                    [
                        "Session_ID",
                        self.session_id
                    ]
                )


                writer.writerow(
                    [
                        "Start_Time",
                        self.session_start_timestamp
                    ]
                )


                writer.writerow(
                    [
                        "Stop_Time",
                        self.session_stop_timestamp
                    ]
                )


                writer.writerow(
                    [
                        "Duration_s",
                        f"{duration:.3f}"
                    ]
                )


                writer.writerow(
                    [
                        "Samples",
                        self.session_sample_count
                    ]
                )


                writer.writerow(
                    [
                        "Maximum_Packet_Gap_ms",
                        f"{self.maximum_packet_gap * 1000.0:.3f}"
                    ]
                )


                # ------------------------------------------------
                # Final values
                # ------------------------------------------------

                if len(self.target_pwm_data) > 0:

                    writer.writerow(
                        [
                            "Final_Target_PWM",
                            self.target_pwm_data[-1]
                        ]
                    )


                if len(self.actual_pwm_data) > 0:

                    writer.writerow(
                        [
                            "Final_Actual_PWM",
                            self.actual_pwm_data[-1]
                        ]
                    )


                if (
                    self.last_target_pwm is not None
                    and self.last_actual_pwm is not None
                ):

                    final_error = (
                        self.last_target_pwm
                        - self.last_actual_pwm
                    )


                    writer.writerow(
                        [
                            "Final_PWM_Error",
                            final_error
                        ]
                    )


                writer.writerow(
                    [
                        "Final_PWM_Status",
                        (
                            "FAULT"
                            if self.pwm_fault_active
                            else "NORMAL"
                        )
                    ]
                )


                if self.current_state is not None:

                    writer.writerow(
                        [
                            "Final_State",
                            self.current_state
                        ]
                    )


            print(
                f"Session summary saved: "
                f"{self.summary_file_path}"
            )


        except Exception as e:

            print(
                f"Session summary error: {e}"
            )


    # ========================================================
    # UART READING
    # ========================================================

    def read_serial(self):

        if self.ser is None:

            return


        try:

            while self.ser.in_waiting:

                raw_line = (
                    self.ser.readline()
                )


                if not raw_line:

                    continue


                line = raw_line.decode(
                    "utf-8",
                    errors="ignore"
                ).strip()


                if not line:

                    continue


                print(line)


                self.parse_line(
                    line
                )


        except Exception as e:

            print(
                f"UART error: {e}"
            )


            self.uart_status_label.setText(
                "UART: ERROR"
            )


    # ========================================================
    # UART PARSER
    # ========================================================

    def parse_line(
        self,
        line
    ):

        # ====================================================
        # IMPORTANT
        #
        # After STOP, ignore all incoming UART data.
        #
        # This guarantees the log represents exactly:
        #
        # START -> STOP
        # ====================================================

        if not self.monitoring:

            return


        # ----------------------------------------------------
        # Expected format:
        #
        # LUX=496 Filtered=533 Stable=546
        # State=CLOUDY Target=999 PWM=480
        #
        # Commas are also supported.
        # ----------------------------------------------------

        pattern = (
            r"LUX\s*=\s*(\d+)"
            r"\s*,?\s+"
            r"Filtered\s*=\s*(\d+)"
            r"\s*,?\s+"
            r"Stable\s*=\s*(\d+)"
            r"\s*,?\s+"
            r"State\s*=\s*"
            r"(NIGHT|CLOUDY|DAYLIGHT|FAULT)"
            r"\s*,?\s+"
            r"Target\s*=\s*(\d+)"
            r"\s*,?\s+"
            r"PWM\s*=\s*(\d+)"
        )


        match = re.search(
            pattern,
            line,
            re.IGNORECASE
        )


        if not match:

            return


        try:

            lux = int(
                match.group(1)
            )

            filtered = int(
                match.group(2)
            )

            stable = int(
                match.group(3)
            )

            state = (
                match.group(4)
                .upper()
            )

            target_pwm = int(
                match.group(5)
            )

            actual_pwm = int(
                match.group(6)
            )


        except ValueError:

            return


        # ====================================================
        # VALIDATE SENSOR VALUES
        # ====================================================

        lux = max(
            0,
            lux
        )

        filtered = max(
            0,
            filtered
        )

        stable = max(
            0,
            stable
        )


        # ====================================================
        # VALIDATE PWM
        # ====================================================

        target_pwm = max(
            0,
            min(
                1000,
                target_pwm
            )
        )

        actual_pwm = max(
            0,
            min(
                1000,
                actual_pwm
            )
        )


        # ====================================================
        # FIRST VALID PACKET OF SESSION
        # ====================================================

        if not self.receiving_data:

            self.receiving_data = True


            current_time = (
                time.monotonic()
            )


            self.last_packet_time = (
                current_time
            )

            self.last_sample_time = (
                current_time
            )


            self.rate_samples.clear()

            self.maximum_packet_gap = 0.0


            self.add_event(
                "Valid STM32 telemetry detected",
                "OK"
            )


        # ====================================================
        # PACKET TIMING
        # ====================================================

        current_time = (
            time.monotonic()
        )


        if self.last_packet_time is not None:

            dt = (
                current_time
                - self.last_packet_time
            )


            if dt > 0:

                if (
                    dt
                    > self.maximum_packet_gap
                ):

                    self.maximum_packet_gap = dt


                instant_rate = (
                    1.0 / dt
                )


                if (
                    0.5
                    <= instant_rate
                    <= 100.0
                ):

                    self.rate_samples.append(
                        instant_rate
                    )


        self.last_packet_time = (
            current_time
        )


        # ====================================================
        # UPDATE DASHBOARD
        # ====================================================

        self.update_dashboard(
            lux,
            filtered,
            stable,
            state,
            target_pwm,
            actual_pwm
        )


    # ========================================================
    # UPDATE DASHBOARD
    # ========================================================

    def update_dashboard(
        self,
        lux,
        filtered,
        stable,
        state,
        target_pwm,
        actual_pwm
    ):

        # ----------------------------------------------------
        # Safety check
        # ----------------------------------------------------

        if not self.monitoring:

            return


        self.sample_number += 1


        # ====================================================
        # REAL ELAPSED TIME
        # ====================================================

        if self.start_time is None:

            self.start_time = (
                time.monotonic()
            )


        elapsed_time = (
            time.monotonic()
            - self.start_time
        )


        # ====================================================
        # STATE HANDLING
        # ====================================================

        if state == "NIGHT":

            condition = NIGHT

            display_state = (
                "NIGHT - HIGH PWM"
            )


        elif state == "CLOUDY":

            condition = CLOUDY

            display_state = (
                "CLOUDY / LOW LIGHT - ADAPTIVE"
            )


        elif state == "DAYLIGHT":

            condition = DAYLIGHT

            display_state = (
                "DAYLIGHT - OFF"
            )


        elif state == "FAULT":

            condition = FAULT

            display_state = (
                "FAULT"
            )


        else:

            condition = CLOUDY

            display_state = (
                "UNKNOWN"
            )


        # ====================================================
        # STATE TRANSITION
        # ====================================================

        if self.current_state != state:

            if self.current_state is not None:

                self.add_event(
                    f"State transition: "
                    f"{self.current_state} -> {state}",
                    "INFO"
                )


            self.current_state = state

            self.state_start_time = (
                elapsed_time
            )


        # ====================================================
        # PREVIOUS TARGET
        # ====================================================

        previous_target_pwm = (
            self.last_target_pwm
        )


        # ====================================================
        # PWM METRICS
        # ====================================================

        (
            pwm_error,
            pwm_tracking,
            pwm_status
        ) = self.calculate_pwm_metrics(
            target_pwm,
            actual_pwm
        )


        # ====================================================
        # TARGET PWM CHANGE EVENT
        # ====================================================

        if (
            previous_target_pwm is not None
            and target_pwm != previous_target_pwm
        ):

            self.add_event(
                f"Target PWM changed: "
                f"{previous_target_pwm} -> {target_pwm}",
                "INFO"
            )


        # ====================================================
        # PWM FAULT EVENT
        # ====================================================

        # calculate_pwm_metrics() already creates the
        # FAULT event when the threshold is reached.


        # ====================================================
        # STORE LIVE GRAPH DATA
        # ====================================================

        self.time_data.append(
            elapsed_time
        )

        self.raw_lux_data.append(
            lux
        )

        self.filtered_lux_data.append(
            filtered
        )

        self.target_pwm_data.append(
            target_pwm
        )

        self.actual_pwm_data.append(
            actual_pwm
        )

        self.condition_data.append(
            condition
        )


        # ====================================================
        # SAVE FULL TELEMETRY SAMPLE
        #
        # This CSV does NOT have the 300-point limitation.
        # Every sample from START -> STOP is saved.
        # ====================================================

        self.log_telemetry(
            lux,
            filtered,
            stable,
            state,
            target_pwm,
            actual_pwm,
            elapsed_time,
            pwm_error,
            pwm_tracking,
            pwm_status
        )


        # ====================================================
        # LIVE VALUES
        # ====================================================

        self.raw_lux_label.setText(
            f"{lux} lux"
        )

        self.filtered_lux_label.setText(
            f"{filtered} lux"
        )

        self.stable_lux_label.setText(
            f"{stable} lux"
        )

        self.target_pwm_label.setText(
            str(target_pwm)
        )

        self.actual_pwm_label.setText(
            str(actual_pwm)
        )

        self.pwm_difference_label.setText(
            f"{pwm_error:+d}"
        )

        self.pwm_tracking_label.setText(
            f"{pwm_tracking:.1f} %"
        )

        self.pwm_status_label.setText(
            pwm_status
        )

        self.state_label.setText(
            display_state
        )


        # ====================================================
        # GRAPH DATA
        # ====================================================

        x = list(
            self.time_data
        )


        self.raw_curve.setData(
            x,
            list(
                self.raw_lux_data
            )
        )


        self.filtered_curve.setData(
            x,
            list(
                self.filtered_lux_data
            )
        )


        self.target_pwm_curve.setData(
            x,
            list(
                self.target_pwm_data
            )
        )


        self.actual_pwm_curve.setData(
            x,
            list(
                self.actual_pwm_data
            )
        )


        self.state_curve.setData(
            x,
            list(
                self.condition_data
            )
        )


        # ====================================================
        # LUX AUTO SCALING
        # ====================================================

        if len(self.raw_lux_data) > 1:

            maximum_lux = max(
                max(
                    self.raw_lux_data
                ),
                max(
                    self.filtered_lux_data
                )
            )


            minimum_lux = min(
                min(
                    self.raw_lux_data
                ),
                min(
                    self.filtered_lux_data
                )
            )


            if maximum_lux <= 0:

                maximum_lux = 100


            margin = max(
                maximum_lux * 0.10,
                10
            )


            self.raw_plot.setYRange(
                max(
                    0,
                    minimum_lux - margin
                ),
                maximum_lux + margin,
                padding=0
            )


            self.filtered_plot.setYRange(
                max(
                    0,
                    minimum_lux - margin
                ),
                maximum_lux + margin,
                padding=0
            )


        # ====================================================
        # ROLLING REAL-TIME WINDOW
        #
        # Only graph display is limited to 15 seconds.
        # CSV logging remains complete.
        # ====================================================

        if len(self.time_data) >= 2:

            newest_time = (
                self.time_data[-1]
            )


            oldest_time = max(
                0.0,
                newest_time
                - GRAPH_WINDOW_SECONDS
            )


            self.raw_plot.setXRange(
                oldest_time,
                newest_time,
                padding=0
            )


            self.filtered_plot.setXRange(
                oldest_time,
                newest_time,
                padding=0
            )


            self.pwm_plot.setXRange(
                oldest_time,
                newest_time,
                padding=0
            )


            self.state_plot.setXRange(
                oldest_time,
                newest_time,
                padding=0
            )


        # ====================================================
        # STATE DURATION
        # ====================================================

        if self.state_start_time is not None:

            state_duration = (
                elapsed_time
                - self.state_start_time
            )


            self.state_duration_label.setText(
                f"STATE TIME: "
                f"{state_duration:.1f} s"
            )


        # ====================================================
        # STATUS VALUES
        # ====================================================

        self.sample_label.setText(
            f"SAMPLES: {self.sample_number}"
        )


        self.last_packet_label.setText(
            f"LAST PACKET: "
            f"{elapsed_time:.1f} s"
        )


        self.packet_gap_label.setText(
            f"MAX GAP: "
            f"{self.maximum_packet_gap * 1000.0:.0f} ms"
        )


    # ========================================================
    # STATUS UPDATE
    # ========================================================

    def update_status(self):

        # ====================================================
        # STM32 / UART
        # ====================================================

        if self.serial_connected:

            self.stm32_status_label.setText(
                "STM32: CONNECTED"
            )

            self.uart_status_label.setText(
                "UART: OK"
            )

        else:

            self.stm32_status_label.setText(
                "STM32: DISCONNECTED"
            )

            self.uart_status_label.setText(
                "UART: ERROR"
            )


        # ====================================================
        # TELEMETRY
        # ====================================================

        if self.receiving_data:

            if self.monitoring:

                self.telemetry_status_label.setText(
                    "TELEMETRY: DATA OK"
                )

            else:

                self.telemetry_status_label.setText(
                    "TELEMETRY: SESSION SAVED"
                )

        else:

            if self.monitoring:

                self.telemetry_status_label.setText(
                    "TELEMETRY: WAITING"
                )

            else:

                self.telemetry_status_label.setText(
                    "TELEMETRY: WAITING"
                )


        # ====================================================
        # MONITOR
        # ====================================================

        if self.monitoring:

            if self.receiving_data:

                self.monitor_status_label.setText(
                    "MONITOR: RUNNING"
                )

            else:

                self.monitor_status_label.setText(
                    "MONITOR: WAITING FOR STM32"
                )

        else:

            self.monitor_status_label.setText(
                "MONITOR: STOPPED"
            )


        # ====================================================
        # TELEMETRY RATE
        # ====================================================

        if len(self.rate_samples) > 0:

            average_rate = (
                sum(
                    self.rate_samples
                )
                / len(
                    self.rate_samples
                )
            )


            self.rate_label.setText(
                f"RATE: {average_rate:.2f} Hz"
            )

        else:

            self.rate_label.setText(
                "RATE: 0.00 Hz"
            )


        # ====================================================
        # TELEMETRY TIMEOUT
        #
        # Timeout is only active while monitoring.
        # ====================================================

        if (
            self.last_packet_time is not None
            and self.monitoring
        ):

            age = (
                time.monotonic()
                - self.last_packet_time
            )


            if age > TELEMETRY_TIMEOUT_S:

                self.telemetry_status_label.setText(
                    "TELEMETRY: TIMEOUT"
                )

                self.monitor_status_label.setText(
                    "MONITOR: STM32 NOT RESPONDING"
                )


                # Add timeout only once

                timeout_already_logged = False


                for event in reversed(
                    self.event_log
                ):

                    if "Telemetry timeout" in event[2]:

                        timeout_already_logged = True

                        break


                if not timeout_already_logged:

                    self.add_event(
                        "Telemetry timeout",
                        "FAULT"
                    )


        # ====================================================
        # STATE DURATION
        # ====================================================

        if (
            self.monitoring
            and self.receiving_data
            and self.start_time is not None
            and self.state_start_time is not None
        ):

            elapsed_time = (
                time.monotonic()
                - self.start_time
            )


            state_duration = (
                elapsed_time
                - self.state_start_time
            )


            self.state_duration_label.setText(
                f"STATE TIME: "
                f"{state_duration:.1f} s"
            )


    # ========================================================
    # EXPORT GRAPHS + CURRENT TELEMETRY
    # ========================================================

    def save_graphs(self):

        # ----------------------------------------------------
        # Check data
        # ----------------------------------------------------

        if len(self.time_data) == 0:

            print(
                "No graph data available."
            )

            self.event_label.setText(
                "EVENT: NO DATA TO EXPORT"
            )

            return


        # ----------------------------------------------------
        # Ask export directory
        # ----------------------------------------------------

        save_directory = (
            QFileDialog.getExistingDirectory(
                self,
                "Select folder to export graphs"
            )
        )


        if not save_directory:

            print(
                "Export cancelled."
            )

            return


        print("")
        print("========================================")
        print("EXPORT GRAPHS")
        print("========================================")
        print(
            f"Export directory: "
            f"{save_directory}"
        )


        # ====================================================
        # GRAPH EXPORT
        # ====================================================

        graph_exports = [
            (
                self.raw_plot,
                "raw_lux.png"
            ),
            (
                self.filtered_plot,
                "filtered_lux.png"
            ),
            (
                self.pwm_plot,
                "pwm_target_actual.png"
            ),
            (
                self.state_plot,
                "lighting_state.png"
            )
        ]


        exported_count = 0


        for plot_widget, filename in graph_exports:

            try:

                file_path = os.path.join(
                    save_directory,
                    filename
                )


                pixmap = plot_widget.grab()


                if pixmap.isNull():

                    print(
                        f"FAILED: {filename} "
                        f"(empty image)"
                    )

                    continue


                success = pixmap.save(
                    file_path,
                    "PNG"
                )


                if (
                    success
                    and os.path.exists(file_path)
                ):

                    file_size = (
                        os.path.getsize(
                            file_path
                        )
                    )


                    if file_size > 0:

                        exported_count += 1

                        print(
                            f"EXPORTED: "
                            f"{file_path}"
                        )

                        print(
                            f"  Size: "
                            f"{file_size} bytes"
                        )

                    else:

                        print(
                            f"FAILED: {filename} "
                            f"(empty file)"
                        )

                else:

                    print(
                        f"FAILED: {filename}"
                    )


            except Exception as e:

                print(
                    f"ERROR exporting "
                    f"{filename}: {e}"
                )


        # ====================================================
        # EXPORT CURRENT GRAPH DATA SNAPSHOT
        # ====================================================

        telemetry_file_path = os.path.join(
            save_directory,
            "telemetry_snapshot.csv"
        )


        try:

            with open(
                telemetry_file_path,
                "w",
                newline="",
                encoding="utf-8"
            ) as data_file:

                writer = csv.writer(
                    data_file
                )


                writer.writerow(
                    [
                        "Elapsed_s",
                        "Raw_Lux",
                        "Filtered_Lux",
                        "Target_PWM",
                        "Actual_PWM",
                        "PWM_Error",
                        "PWM_Tracking_Percent",
                        "State"
                    ]
                )


                for i in range(
                    len(self.time_data)
                ):

                    elapsed_s = (
                        self.time_data[i]
                    )

                    raw_lux = (
                        self.raw_lux_data[i]
                    )

                    filtered_lux = (
                        self.filtered_lux_data[i]
                    )

                    target_pwm = (
                        self.target_pwm_data[i]
                    )

                    actual_pwm = (
                        self.actual_pwm_data[i]
                    )

                    pwm_error = (
                        target_pwm
                        - actual_pwm
                    )


                    # Calculate tracking

                    if target_pwm == 0:

                        if actual_pwm == 0:

                            tracking = 100.0

                        else:

                            tracking = 0.0

                    else:

                        tracking = (
                            100.0
                            * (
                                1.0
                                - (
                                    abs(
                                        pwm_error
                                    )
                                    / float(
                                        target_pwm
                                    )
                                )
                            )
                        )


                        tracking = max(
                            0.0,
                            min(
                                100.0,
                                tracking
                            )
                        )


                    condition = (
                        self.condition_data[i]
                    )


                    if condition == NIGHT:

                        state_text = "NIGHT"

                    elif condition == CLOUDY:

                        state_text = "CLOUDY"

                    elif condition == DAYLIGHT:

                        state_text = "DAYLIGHT"

                    elif condition == FAULT:

                        state_text = "FAULT"

                    else:

                        state_text = "UNKNOWN"


                    writer.writerow(
                        [
                            f"{elapsed_s:.3f}",
                            raw_lux,
                            filtered_lux,
                            target_pwm,
                            actual_pwm,
                            pwm_error,
                            f"{tracking:.2f}",
                            state_text
                        ]
                    )


            print(
                f"EXPORTED: "
                f"{telemetry_file_path}"
            )


        except Exception as e:

            print(
                f"ERROR exporting telemetry: "
                f"{e}"
            )


        # ====================================================
        # EXPORT EVENT HISTORY
        # ====================================================

        event_file_path = os.path.join(
            save_directory,
            "event_log.csv"
        )


        try:

            with open(
                event_file_path,
                "w",
                newline="",
                encoding="utf-8"
            ) as event_file:

                writer = csv.writer(
                    event_file
                )


                writer.writerow(
                    [
                        "Timestamp",
                        "Elapsed_s",
                        "Event",
                        "Severity"
                    ]
                )


                for event in self.event_log:

                    writer.writerow(
                        [
                            event[0],
                            f"{event[1]:.3f}",
                            event[2],
                            event[3]
                        ]
                    )


            print(
                f"EXPORTED: "
                f"{event_file_path}"
            )


        except Exception as e:

            print(
                f"ERROR exporting event log: "
                f"{e}"
            )


        # ====================================================
        # FINAL EXPORT STATUS
        # ====================================================

        print("")
        print("----------------------------------------")
        print(
            f"EXPORT COMPLETE: "
            f"{exported_count}/4 graphs"
        )
        print("----------------------------------------")
        print("")


        if exported_count == 4:

            self.event_label.setText(
                "EVENT: EXPORT COMPLETE"
            )

        else:

            self.event_label.setText(
                f"EVENT: EXPORT "
                f"{exported_count}/4 GRAPHS"
            )


    # ========================================================
    # CLOSE EVENT
    # ========================================================

    def closeEvent(
        self,
        event
    ):

        # ----------------------------------------------------
        # If user closes application while monitoring,
        # save the session first.
        # ----------------------------------------------------

        if self.monitoring:

            self.stop_monitoring()


        # ----------------------------------------------------
        # Stop timers
        # ----------------------------------------------------

        if self.timer.isActive():

            self.timer.stop()


        if self.status_timer.isActive():

            self.status_timer.stop()


        # ----------------------------------------------------
        # Close any remaining log files
        # ----------------------------------------------------

        self.close_log_files()


        # ----------------------------------------------------
        # Close UART
        # ----------------------------------------------------

        if (
            self.ser is not None
            and self.ser.is_open
        ):

            self.ser.close()

            print(
                "Serial connection closed."
            )


        event.accept()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    app = QApplication(
        sys.argv
    )


    window = HeadlightDashboard()

    window.show()


    sys.exit(
        app.exec()
    )
