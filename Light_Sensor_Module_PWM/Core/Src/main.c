/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "stdio.h"
#include "string.h"

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define BH1750_ADDR  0x46
#define MAX_PWM             999
#define MAX_LUX             5000
#define DAYLIGHT_LUX        2500
#define DARK_LUX             500
#define LUX_HYSTERESIS      20
#define NIGHT_PWM_STEP      100
#define ADAPTIVE_PWM_STEP   10
#define N 5

#define BME280_ADDR_76  0xEC   // 0xEC
#define BME280_ADDR_77  0xEE  // 0xEE
#define BME280_ID_REG   0xD0
#define BME280_CHIP_ID  0x60

#define NIGHT_ENTER_LUX       500U
#define NIGHT_EXIT_LUX        600U

#define DAYLIGHT_ENTER_LUX    2000U
#define DAYLIGHT_EXIT_LUX     1800U

#define NIGHT_ENTER_QUALIFICATION_MS       500U
#define NIGHT_EXIT_QUALIFICATION_MS        300U

#define DAYLIGHT_ENTER_QUALIFICATION_MS   2000U
#define DAYLIGHT_EXIT_QUALIFICATION_MS     300U

#define PWM_STEP                 10U

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
I2C_HandleTypeDef hi2c1;

TIM_HandleTypeDef htim3;

UART_HandleTypeDef huart2;

/* USER CODE BEGIN PV */
uint16_t lux;
uint16_t raw_value;
char msg[100];
uint32_t RAW;
uint8_t cmd = 0x10;
uint8_t data[2];
uint32_t sum;
uint32_t Filtered_LUX;
uint32_t target_pwm;
uint32_t pwm_value = 0 ;


/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_I2C1_Init(void);
static void MX_TIM3_Init(void);
static void MX_USART2_UART_Init(void);
/* USER CODE BEGIN PFP */
void Update_Light_State(uint32_t lux);
void Adaptive_PWM(void);

static uint32_t state_change_start = 0;
static uint8_t transition_pending = 0;

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
typedef enum {
	LIGHT_NIGHT = 0,
	LIGHT_CLOUDY,
	LIGHT_DAYLIGHT,
	LIGHT_FAULT

} LightState_t;

static LightState_t light_state = LIGHT_CLOUDY;
static LightState_t pending_state = LIGHT_CLOUDY;
static uint8_t sensor_fault = 0;
static uint32_t sensor_fault_count = 0;
static uint32_t last_valid_lux = 0;

void I2C_Test(void){
	if(HAL_I2C_IsDeviceReady(&hi2c1,BH1750_ADDR,3,100)==HAL_OK){
		sprintf(msg,"BH1750 Sensor is Connected\r\n");
		HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);
	}
	else{
		sprintf(msg,"BH1750 Sensor is Not Connected\r\n");
		HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);
	}
}
void BH1750_Start_Read(void){
	HAL_I2C_Master_Transmit(&hi2c1,BH1750_ADDR,&cmd,1,HAL_MAX_DELAY);
	sprintf(msg, "Data is Transmitted\r\n");
	HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);

	HAL_I2C_Master_Receive(&hi2c1,BH1750_ADDR,data,2,HAL_MAX_DELAY);
	sprintf(msg,"Data = %02X,%02X \r\n",data[0],data[1]);
	HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);

	/* Converting 2 data bytes to Raw data of BH1750*/
	raw_value = ((uint16_t)data[0] << 8) | data[1];
	sprintf(msg,"raw_value  =%u \r\n",raw_value);
	HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);

	/* Converting raw values to Lux */
	lux =(raw_value * 10)/12;
	sprintf(msg,"LUX  =%u \r\n",lux);
	HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);


}
void BH1750_ReadLux(void){

	if(HAL_I2C_Master_Receive(&hi2c1,BH1750_ADDR,data,2,HAL_MAX_DELAY)==HAL_OK){
	RAW = ((uint16_t)data[0] << 8) | data[1];
	lux =(RAW * 10)/12;
	sprintf(msg,"RAW = %lu,LUX  =%u \r\n",RAW,lux);
	HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);
	}
	else{
		sprintf(msg,"Sensor is not providing data \r\n");
		HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);
	}

}
void BH1750_PWM_LED(void){
	if(lux<=50){
		__HAL_TIM_SET_COMPARE(&htim3,TIM_CHANNEL_2,999);
		sprintf(msg,"Light is Dark\r\n");
		HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);
	}
	else if(lux <=200){
		__HAL_TIM_SET_COMPARE(&htim3,TIM_CHANNEL_2,750);
		sprintf(msg,"Light is Dim \r\n");
		HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);

	}
	else if( lux <=2000){
		__HAL_TIM_SET_COMPARE(&htim3,TIM_CHANNEL_2,500);
		sprintf(msg,"Light is Moderate \r\n");
		HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);

	}
	else if(lux <=10000){
		__HAL_TIM_SET_COMPARE(&htim3,TIM_CHANNEL_2,250);
		sprintf(msg,"Light is Bright\r\n");
		HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);

	}
	else {
		__HAL_TIM_SET_COMPARE(&htim3,TIM_CHANNEL_2,0);
		sprintf(msg, "Ambient Light Very Bright - LED OFF\r\n");
		HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);


	}

}
void Filtered_Lux(void){
	static uint32_t filtered = 0;
	static uint8_t filter_initialized = 0;
	HAL_StatusTypeDef status;

	/*===========================BH1750 SENSOR READ=================*/

	status = HAL_I2C_Master_Receive(&hi2c1,BH1750_ADDR,data,2,100);

	/*==================== I2C COMMUNICATION FAULT =====================*/
	if(status != HAL_OK){
		sensor_fault = 1;
		sensor_fault_count++;
		sprintf(msg,"FAULT: BH1750 I2C ERROR\r\n");
		HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);
		return;

	}
	/*================ CONVERT SENSOR DATA ==================*/
	RAW = ((uint16_t)data[0] << 8) | data[1];
	lux =(RAW * 10U)/12U;
	/*================= RANGE VALIDATION ===================*/
    if (lux > 100000U)
    {
        sensor_fault = 1;
        sensor_fault_count++;

        return;
    }
    sensor_fault = 0;

    last_valid_lux = lux;

	if (!filter_initialized){
		filtered = lux;
		filter_initialized = 1;

	}
	else
	{
		/* ================ IIR FIRST ORDER FILTER ===============*/
		filtered = ((filtered * 3U) + lux ) / 4U;
	}
	Filtered_LUX = filtered;
	sprintf(msg,"LUX = %lu, FILTERED_LUX = %lu\r\n",(unsigned long)lux,(unsigned long)Filtered_LUX);
	HAL_UART_Transmit(&huart2,(uint8_t*)msg,strlen(msg),HAL_MAX_DELAY);



}

void Adaptive_PWM(void)
{
    static uint32_t stable_lux = 0;
    static uint8_t first_reading = 1;

    uint32_t light_lux;

    /* --------------------------------
       1. Lux hysteresis
       -------------------------------- */

    if (first_reading ||
        (Filtered_LUX > stable_lux &&
         (Filtered_LUX - stable_lux) >= LUX_HYSTERESIS) ||
        (stable_lux > Filtered_LUX &&
         (stable_lux - Filtered_LUX) >= LUX_HYSTERESIS))
    {
        stable_lux = Filtered_LUX;
        first_reading = 0;
    }

    light_lux = stable_lux;
    /* =============== UPDATE LIGHT STATE =========== */
    if(sensor_fault){
    	light_state = LIGHT_FAULT;
    }
    else
    {
    	Update_Light_State(light_lux);
    }

    /*=======PWM CONTROL BASED ON STATE===========*/
    switch(light_state){

    case LIGHT_NIGHT:
    	/*
    	 * Dark environment.
    	 *
    	 * Full headlight immediately after
    	 * the night condition has been qualified.
    	 */

		target_pwm = MAX_PWM;

		pwm_value = MAX_PWM;

    	break;

    	/*============ CLOUDY / LOW LIGHT ========*/
    case LIGHT_CLOUDY:
        /*
         * Adaptive PWM.
         *
         * 600 lux  -> approximately maximum PWM
         * 2000 lux -> approximately zero PWM
         */

        if (light_lux <= NIGHT_EXIT_LUX)
        {
            target_pwm = MAX_PWM;
        }
        else if (light_lux >= DAYLIGHT_ENTER_LUX)
        {
            target_pwm = 0U;
        }
        else
        {
            target_pwm =
                ((DAYLIGHT_ENTER_LUX - light_lux)
                 * MAX_PWM) /
                (DAYLIGHT_ENTER_LUX - NIGHT_EXIT_LUX);
        }


        /* ---------------------------------------------
           Smooth PWM adjustment
           --------------------------------------------- */

        if (pwm_value < target_pwm)
        {
            if ((target_pwm - pwm_value) <= PWM_STEP)

            {
                pwm_value = target_pwm;
            }
            else
            {
                pwm_value += PWM_STEP;
            }
        }
        else if (pwm_value > target_pwm)
        {
            if ((pwm_value - target_pwm) <= PWM_STEP)
            {
                pwm_value = target_pwm;
            }
            else
            {
                pwm_value -= PWM_STEP;
            }
        }

        break;

    case LIGHT_DAYLIGHT:

    	/*
         * Strong daylight.
         *
         * Headlight OFF immediately once daylight
         * has been temporally qualified.
         */

        target_pwm = 0;

        pwm_value = 0;

        break;

    case LIGHT_FAULT:
    	/* ===== SENSOR FAILURE ===========*/
        target_pwm = 500;

        pwm_value = 500;



    default:

        target_pwm = 0;
        pwm_value = 0;

        break;

    }
    /* =====================================================
       4. APPLY PWM
       ===================================================== */

    __HAL_TIM_SET_COMPARE(
        &htim3,
        TIM_CHANNEL_2,
        pwm_value
    );


    /* =====================================================
       5. UART DEBUG
       ===================================================== */

    const char *state_text;

    switch (light_state)
    {
        case LIGHT_NIGHT:
            state_text = "NIGHT";
            break;

        case LIGHT_CLOUDY:
            state_text = "CLOUDY";
            break;

        case LIGHT_DAYLIGHT:
            state_text = "DAYLIGHT";
            break;

        case LIGHT_FAULT:
        	state_text = "FAULT";
        	break;

        default:
            state_text = "UNKNOWN";
            break;
    }


    snprintf(
        msg,
        sizeof(msg),

        "LUX=%lu Filtered=%lu Stable=%lu "
        "State=%s Target=%lu PWM=%lu\r\n",

        (unsigned long)lux,

        (unsigned long)Filtered_LUX,

        (unsigned long)light_lux,

        state_text,

        (unsigned long)target_pwm,

        (unsigned long)pwm_value
    );


    HAL_UART_Transmit(
        &huart2,
        (uint8_t *)msg,
        strlen(msg),
        HAL_MAX_DELAY
    );
}

void Update_Light_State(uint32_t lux){
    uint32_t now = HAL_GetTick();

    LightState_t requested_state = light_state;
    uint32_t qualification_time = 0U;
    /*================== STATE MACHINE =====================*/
    switch(light_state){

    case LIGHT_NIGHT:
    	/**============NIGHT=======*/
        if (lux > NIGHT_EXIT_LUX)
        {
            requested_state = LIGHT_CLOUDY;
            qualification_time = NIGHT_EXIT_QUALIFICATION_MS;
        }

        break;

        /*======== CLOUDY TO NIGHT=======*/
    case LIGHT_CLOUDY:

    	if (lux < NIGHT_ENTER_LUX)
    	{
    	    requested_state = LIGHT_NIGHT;
    	    qualification_time = NIGHT_ENTER_QUALIFICATION_MS;
    	}
    	else if(lux > DAYLIGHT_ENTER_LUX){
    		requested_state = LIGHT_DAYLIGHT;
    		qualification_time = DAYLIGHT_ENTER_QUALIFICATION_MS;

    	}

    	break;
    case LIGHT_DAYLIGHT:
    	/*=========Daylight -> Cloudy========*/
        if (lux < DAYLIGHT_EXIT_LUX)
        {
            requested_state = LIGHT_CLOUDY;
            qualification_time = DAYLIGHT_EXIT_QUALIFICATION_MS;
        }

        break;


    default:

        light_state = LIGHT_CLOUDY;
        transition_pending = 0U;

        break;

    }

    /*==================TEMPORAL QUALIFICATION*/
    if (requested_state != light_state)
        {
            /* New transition candidate */

            if (!transition_pending || pending_state != requested_state)
            {
                pending_state = requested_state;

                state_change_start = now;

                transition_pending = 1U;
            }


            /* Has the condition remained valid long enough? */

            if ((now - state_change_start) >= qualification_time)
            {
                light_state = pending_state;

                transition_pending = 0U;
            }
        }
        else
        {
            /*
             * Condition disappeared before
             * qualification completed.
             */

            transition_pending = 0U;
        }
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_I2C1_Init();
  MX_TIM3_Init();
  MX_USART2_UART_Init();
  /* USER CODE BEGIN 2 */
  HAL_TIM_PWM_Start(&htim3,TIM_CHANNEL_2);
//  I2C_Test();
//  BH1750_ReadLux();
	BH1750_Start_Read();

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

//	  BH1750_ReadLux();
//	  BH1750_PWM_LED();
//	  HAL_Delay(1000);
	  Filtered_Lux();
	  Adaptive_PWM();
	  HAL_Delay(50);


    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE2);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = 16;
  RCC_OscInitStruct.PLL.PLLN = 336;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV4;
  RCC_OscInitStruct.PLL.PLLQ = 7;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief I2C1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_I2C1_Init(void)
{

  /* USER CODE BEGIN I2C1_Init 0 */

  /* USER CODE END I2C1_Init 0 */

  /* USER CODE BEGIN I2C1_Init 1 */

  /* USER CODE END I2C1_Init 1 */
  hi2c1.Instance = I2C1;
  hi2c1.Init.ClockSpeed = 100000;
  hi2c1.Init.DutyCycle = I2C_DUTYCYCLE_2;
  hi2c1.Init.OwnAddress1 = 0;
  hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c1.Init.OwnAddress2 = 0;
  hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&hi2c1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN I2C1_Init 2 */

  /* USER CODE END I2C1_Init 2 */

}

/**
  * @brief TIM3 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM3_Init(void)
{

  /* USER CODE BEGIN TIM3_Init 0 */

  /* USER CODE END TIM3_Init 0 */

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIM_OC_InitTypeDef sConfigOC = {0};

  /* USER CODE BEGIN TIM3_Init 1 */

  /* USER CODE END TIM3_Init 1 */
  htim3.Instance = TIM3;
  htim3.Init.Prescaler = 83;
  htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim3.Init.Period = 999;
  htim3.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim3.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim3) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim3, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_TIM_PWM_Init(&htim3) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim3, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfigOC.OCMode = TIM_OCMODE_PWM1;
  sConfigOC.Pulse = 0;
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  if (HAL_TIM_PWM_ConfigChannel(&htim3, &sConfigOC, TIM_CHANNEL_2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM3_Init 2 */

  /* USER CODE END TIM3_Init 2 */
  HAL_TIM_MspPostInit(&htim3);

}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART2_UART_Init(void)
{

  /* USER CODE BEGIN USART2_Init 0 */

  /* USER CODE END USART2_Init 0 */

  /* USER CODE BEGIN USART2_Init 1 */

  /* USER CODE END USART2_Init 1 */
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 115200;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART2_Init 2 */

  /* USER CODE END USART2_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(LD2_GPIO_Port, LD2_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin : B1_Pin */
  GPIO_InitStruct.Pin = B1_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_FALLING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(B1_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pin : LD2_Pin */
  GPIO_InitStruct.Pin = LD2_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LD2_GPIO_Port, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
