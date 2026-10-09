package main

import (
	"example.com/gym_bot/import_script"
	"example.com/gym_bot/pkg/database_service"
	"github.com/tealeg/xlsx"
	"log"
)

func main() {
	// 1. Загрузите конфигурацию базы данных
	_, err := database_service.LoadConfig()
	if err != nil {
		log.Fatal("Failed to load database configuration:", err)
	}

	// 2. Установите соединение с базой данных
	db, err := database_service.InitConnection()
	if err != nil {
		log.Fatal("Failed to connect to the database:", err)
	}
	defer db.Close()

	// 3. Откройте файл xlsx
	xlFile, err := xlsx.OpenFile("import_script/schedule_usr.xlsx")
	if err != nil {
		log.Fatal("Failed to open xlsx file:", err)
	}

	// 4. Загрузите справочные таблицы
	allDates, err := import_script.LoadAllDates(db)
	if err != nil {
		log.Fatal("Failed to load all_dates:", err)
	}

	slots, err := import_script.LoadSlots(db)
	if err != nil {
		log.Fatal("Failed to load slots:", err)
	}

	programNames, err := import_script.LoadProgramNames(db)
	if err != nil {
		log.Fatal("Failed to load program_names:", err)
	}

	// 5. Импортируйте данные из файла xlsx в таблицу "schedule"
	err = import_script.ImportSchedule(db, xlFile, allDates, slots, programNames)
	if err != nil {
		log.Fatal("Failed to import schedule:", err)
	}
}
