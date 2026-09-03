# Real-Time Adaptive Headlight Control System

My first solo embedded-systems project was the development and implementation of a **Real-Time Adaptive Headlight Control System** using an **STM32 NUCLEO-F401RE**.

Previously, I had worked with individual peripherals and small firmware modules. With this project, I focused on bringing multiple hardware and software components together into a complete, real-time embedded system.

## Project Overview

The system continuously measures ambient light, processes and filters the sensor data, determines the current lighting condition, and dynamically controls an external LED headlight using PWM.

### System Flow

**Ambient Light → BH1750 → I²C → STM32 + RTOS → Lighting Decision → PWM → LED Headlight**

The controller adapts the headlight output according to the detected lighting condition:

- **Daylight** → Low / zero headlight output
- **Dusk / Cloudy** → Adaptive intermediate brightness
- **Night** → High headlight brightness
- **Fault** → Defined safe-state behavior

## RTOS-Based Firmware Architecture

The firmware was developed using **CMSIS-RTOS2** with independent tasks running at different priorities.

### Sensor Task
- Periodically acquires ambient-light measurements
- Processes and filters sensor data
- Maintains filtered and stable lux values

### Headlight Task
- Evaluates the current lighting condition
- Implements lighting-state transitions
- Calculates the required PWM target
- Updates the LED headlight output

### Monitor Task
- Monitors system behaviour
- Tracks target versus actual PWM
- Calculates PWM error and tracking performance
- Supports fault detection and system diagnostics

This task-based architecture allowed me to implement **priority-based scheduling, periodic execution, state transitions, actuator control, and fault monitoring** as part of one integrated real-time system.

## Adaptive Headlight Control

The controller does not simply switch the headlight ON or OFF. It continuously adjusts the PWM output according to ambient-light conditions.

The control path is:

**Lux Measurement → Filtering → Stable Lux → Lighting State → Target PWM → Actual PWM**

The implementation includes:

- Ambient-light filtering
- Hysteresis-based state transitions
- Temporal state qualification
- Adaptive PWM ramping
- Target versus actual PWM tracking
- PWM error calculation
- Fault detection
- Safe-state handling

These mechanisms improve stability and prevent unnecessary state changes caused by short-term sensor fluctuations.

## Hardware & Interfaces

### Microcontroller
- STM32 NUCLEO-F401RE

### Sensors
- BH1750 Ambient Light Sensor


### Actuator
- External LED Headlight

### Communication & Control Interfaces

| Interface | Purpose |
|-----------|---------|
| **I²C** | BH1750 sensor communication |
| **TIM3 PWM** | LED headlight brightness control |
| **UART** | Real-time telemetry to PC dashboard |

## Real-Time Monitoring Dashboard

I developed a PC-based monitoring dashboard to observe the embedded system while it is running.

The dashboard provides real-time visibility into:

- Raw Lux
- Filtered Lux
- Stable Lux
- Lighting State
- Target PWM
- Actual PWM
- PWM Error
- PWM Tracking %
- STM32 connection status
- Telemetry status

### Monitoring Flow

**STM32 → UART → PC Dashboard → Real-Time Visualization**

The dashboard also includes **session logging**, capturing telemetry from **START → STOP** so that the complete system behaviour can be reviewed and analysed after a test run.

## Architecture

The project is documented through multiple architecture levels:

- [System-Level Architecture](Architectures/System_Level_Architecture.png)
- [Hardware Architecture](Architectures/Hardware%20Architecture-selection.png)
- [Firmware / RTOS Architecture](Architectures/Firmware%20Architecture.png)
- [Adaptive PWM Architecture](Architectures/Adaptive_PWM_Architecture.png)
- [Adaptive State Control Architecture](Architectures/Adaptive_StateControl_%20Architecture.png)
- [Communication Architecture](Architectures/Communication_Architecture.png)
- [Control & Monitoring Architecture](Architectures/Control%20%26%20Monitoring%20Architecture-selection.png)

## Development Focus

This project gave me practical experience integrating:

**STM32 HAL + CMSIS-RTOS2 + I²C + UART + PWM + Sensor Filtering + State Machines + Real-Time Scheduling + Fault Monitoring + Data Visualization**

Rather than developing each peripheral independently, I implemented and integrated them into a complete **Sense → Process → Decide → Actuate → Monitor → Diagnose** cycle.

## Current Status

The core real-time adaptive headlight control system has been **developed and implemented**.

I am continuing to extend the project toward a more **automotive-oriented embedded architecture**, with additional communication, diagnostics, testing, and system-level validation.

## Project Goals

The main objective of this project was to gain practical experience in designing and implementing a real-time embedded system from the ground up, including:

- Hardware and peripheral integration
- RTOS task architecture
- Real-time scheduling
- Sensor data processing
- Control logic
- PWM actuator control
- Fault detection
- Telemetry
- Real-time monitoring
- Post-test data analysis

---

### Key Technologies

**STM32 NUCLEO-F401RE | STM32 HAL | CMSIS-RTOS2 | BH1750 | BME280 | I²C | SPI | UART | PWM | MCP2515 CAN | Python | Real-Time Dashboard**
