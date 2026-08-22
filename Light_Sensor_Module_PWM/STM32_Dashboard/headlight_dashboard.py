import sys
import re
import serial

from collections import deque

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QGridLayout,
    QLabel,
    QGroupBox
)

import pyqtgraph as pg


# ============================================================
# STM32 UART CONFIGURATION
# ============================================================

SERIAL_PORT = "/dev/cu.usbmodem1303"
BAUD_RATE = 115200

# Number of samples visible in graphs
MAX_POINTS = 300


# ============================================================
# HEADLIGHT CONTROL THRESHOLDS
# ============================================================

DAYLIGHT_LUX = 2000
DARK_LUX = 500


# Lighting condition values for graph
NIGHT = 0
CLOUDY = 1
DAYLIGHT = 2


# ============================================================
# DASHBOARD
# ============================================================

class HeadlightDashboard(QWidget):

    def __init__(self):

        super().__init__()

        # ----------------------------------------------------
        # Window
        # ----------------------------------------------------

        self.setWindowTitle(
            "STM32 Automatic Headlight Monitor"
        )

        self.resize(1400, 1000)


        # ----------------------------------------------------
        # Serial connection
        # ----------------------------------------------------

        self.ser = None

        try:

            self.ser = serial.Serial(
                SERIAL_PORT,
                BAUD_RATE,
                timeout=0.01
            )

            print(
                f"Connected to {SERIAL_PORT}"
            )

        except Exception as e:

            print(
                f"Serial connection failed: {e}"
            )


        # ----------------------------------------------------
        # Data buffers
        # ----------------------------------------------------

        self.sample_number = 0

        self.time_data = deque(
            maxlen=MAX_POINTS
        )

        self.raw_lux_data = deque(
            maxlen=MAX_POINTS
        )

        self.filtered_lux_data = deque(
            maxlen=MAX_POINTS
        )

        self.pwm_data = deque(
            maxlen=MAX_POINTS
        )

        self.condition_data = deque(
            maxlen=MAX_POINTS
        )


        # ----------------------------------------------------
        # Build UI
        # ----------------------------------------------------

        self.setup_ui()


        # ----------------------------------------------------
        # UART polling timer
        # ----------------------------------------------------

        self.timer = QTimer()

        self.timer.timeout.connect(
            self.read_serial
        )

        self.timer.start(20)


    # ========================================================
    # USER INTERFACE
    # ========================================================

    def setup_ui(self):

        main_layout = QVBoxLayout()

        main_layout.setSpacing(10)


        # ====================================================
        # TITLE
        # ====================================================

        title = QLabel(
            "STM32 AUTOMATIC HEADLIGHT MONITOR"
        )

        title.setStyleSheet(
            """
            QLabel {
                font-size: 28px;
                font-weight: bold;
                padding: 10px;
            }
            """
        )

        main_layout.addWidget(title)


        # ====================================================
        # LIVE VALUES BOX
        # ====================================================

        values_box = QGroupBox(
            "Live Sensor / Controller Data"
        )

        values_layout = QGridLayout()

        values_layout.setHorizontalSpacing(40)
        values_layout.setVerticalSpacing(10)


        # ----------------------------------------------------
        # Labels
        # ----------------------------------------------------

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

        self.pwm_label = QLabel(
            "0"
        )

        self.state_label = QLabel(
            "UNKNOWN"
        )


        # Make values slightly larger

        value_style = """
            QLabel {
                font-size: 18px;
                font-weight: bold;
            }
        """

        self.raw_lux_label.setStyleSheet(
            value_style
        )

        self.filtered_lux_label.setStyleSheet(
            value_style
        )

        self.stable_lux_label.setStyleSheet(
            value_style
        )

        self.target_pwm_label.setStyleSheet(
            value_style
        )

        self.pwm_label.setStyleSheet(
            value_style
        )

        self.state_label.setStyleSheet(
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
            self.pwm_label,
            2,
            1
        )


        values_layout.addWidget(
            QLabel("Headlight State:"),
            2,
            2
        )

        values_layout.addWidget(
            self.state_label,
            2,
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
            "Samples"
        )

        self.raw_plot.showGrid(
            x=True,
            y=True,
            alpha=0.3
        )

        self.raw_plot.setMinimumHeight(
            200
        )

        self.raw_curve = self.raw_plot.plot(
            pen=pg.mkPen(
                width=2
            )
        )

        main_layout.addWidget(
            self.raw_plot
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
            "Samples"
        )

        self.filtered_plot.showGrid(
            x=True,
            y=True,
            alpha=0.3
        )

        self.filtered_plot.setMinimumHeight(
            200
        )

        self.filtered_curve = self.filtered_plot.plot(
            pen=pg.mkPen(
                width=2
            )
        )

        main_layout.addWidget(
            self.filtered_plot
        )
        # ====================================================
        # GRAPH 3 - ACTUAL PWM
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
            "Samples"
        )

        self.pwm_plot.setYRange(
            0,
            1000
        )

        self.pwm_plot.showGrid(
            x=True,
            y=True,
            alpha=0.3
        )

        self.pwm_plot.setMinimumHeight(
            200
        )

        self.pwm_curve = self.pwm_plot.plot(
            pen=pg.mkPen(
                width=2
            )
        )

        main_layout.addWidget(
            self.pwm_plot
        )


        # ====================================================
        # GRAPH 4 - LIGHTING CONDITION
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
            "Samples"
        )

        self.state_plot.setYRange(
            -0.2,
            2.2
        )

        self.state_plot.showGrid(
            x=True,
            y=True,
            alpha=0.3
        )

        self.state_plot.setMinimumHeight(
            200
        )



        # ----------------------------------------------------
        # IMPORTANT:
        #
        # setTicks() belongs to the AXIS,
        # not PlotWidget.
        # ----------------------------------------------------

        self.state_plot.getAxis(
            "left"
        ).setTicks(
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
                    )
                ]
            ]
        )


        self.state_curve = self.state_plot.plot(
            pen=pg.mkPen(
                width=3
            ),
            symbol="o",
            symbolSize=5
        )


        main_layout.addWidget(
            self.state_plot
        )


        # ====================================================
        # FINAL UI
        # ====================================================

        self.setLayout(
            main_layout
        )


    # ========================================================
    # UART READING
    # ========================================================

    def read_serial(self):

        if self.ser is None:

            return


        try:

            while self.ser.in_waiting:

                raw_line = self.ser.readline()


                if not raw_line:

                    continue


                line = raw_line.decode(
                    "utf-8",
                    errors="ignore"
                ).strip()


                if not line:

                    continue


                # Show STM32 data in terminal
                print(line)


                # Parse telemetry
                self.parse_line(line)


        except Exception as e:

            print(
                "UART error:",
                e
            )


    # ========================================================
    # PARSE STM32 TELEMETRY
    # ========================================================

    def parse_line(
        self,
        line
    ):

        """
        Supports:

        LUX=24 Filtered=24 Stable=24 Target=999 PWM=800

        and also:

        LUX=24, Filtered=24, Stable=24, Target=999, PWM=800
        """


        pattern = (
            r"LUX\s*=\s*(\d+)"
            r"[,\s]+"
            r"Filtered\s*=\s*(\d+)"
            r"[,\s]+"
            r"Stable\s*=\s*(\d+)"
            r"[,\s]+"
            r"Target\s*=\s*(\d+)"
            r"[,\s]+"
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

            target_pwm = int(
                match.group(4)
            )

            pwm = int(
                match.group(5)
            )


        except ValueError:

            return


        self.update_dashboard(
            lux,
            filtered,
            stable,
            target_pwm,
            pwm
        )


    # ========================================================
    # UPDATE DASHBOARD
    # ========================================================

    def update_dashboard(
        self,
        lux,
        filtered,
        stable,
        target_pwm,
        pwm
    ):

        self.sample_number += 1


        # ----------------------------------------------------
        # Store data
        # ----------------------------------------------------

        self.time_data.append(
            self.sample_number
        )

        self.raw_lux_data.append(
            lux
        )

        self.filtered_lux_data.append(
            filtered
        )

        self.pwm_data.append(
            pwm
        )


        # ----------------------------------------------------
        # Determine lighting condition
        # ----------------------------------------------------

        if stable >= DAYLIGHT_LUX:

            condition = DAYLIGHT

            state = "DAYLIGHT - OFF"


        elif stable < DARK_LUX:

            condition = NIGHT

            state = "NIGHT - HIGH PWM"


        else:

            condition = CLOUDY

            state = "CLOUDY / LOW LIGHT - ADAPTIVE"


        self.condition_data.append(
            condition
        )


        # ----------------------------------------------------
        # Update live values
        # ----------------------------------------------------

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

        self.pwm_label.setText(
            str(pwm)
        )

        self.state_label.setText(
            state
        )


        # ----------------------------------------------------
        # Update graphs
        # ----------------------------------------------------

        x = list(
            self.time_data
        )


        # GRAPH 1
        self.raw_curve.setData(
            x,
            list(
                self.raw_lux_data
            )
        )


        # GRAPH 2
        self.filtered_curve.setData(
            x,
            list(
                self.filtered_lux_data
            )
        )
        # GRAPH 3
        self.pwm_curve.setData(
            x,
            list(
                self.pwm_data
            )
        )


        # GRAPH 4
        self.state_curve.setData(
            x,
            list(
                self.condition_data
            )
        )



        # ----------------------------------------------------
        # Automatically adjust Lux graph range
        # ----------------------------------------------------

        if len(self.raw_lux_data) > 1:

            maximum_lux = max(
                max(self.raw_lux_data),
                max(self.filtered_lux_data)
            )

            minimum_lux = min(
                min(self.raw_lux_data),
                min(self.filtered_lux_data)
            )


            # Add some margin

            if maximum_lux <= 0:

                maximum_lux = 100


            margin = maximum_lux * 0.10


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


        # ----------------------------------------------------
        # Keep graphs focused on recent samples
        # ----------------------------------------------------

        if self.sample_number > MAX_POINTS:

            minimum_x = (
                self.sample_number
                - MAX_POINTS
            )

            maximum_x = self.sample_number

            self.raw_plot.setXRange(
                minimum_x,
                maximum_x,
                padding=0
            )

            self.filtered_plot.setXRange(
                minimum_x,
                maximum_x,
                padding=0
            )

            self.pwm_plot.setXRange(
                minimum_x,
                maximum_x,
                padding=0
            )

            self.state_plot.setXRange(
                minimum_x,
                maximum_x,
                padding=0
            )


    # ========================================================
    # CLOSE EVENT
    # ========================================================

    def closeEvent(
        self,
        event
    ):

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
