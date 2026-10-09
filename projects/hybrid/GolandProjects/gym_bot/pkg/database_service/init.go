package database_service

import (
	"database/sql"
	"fmt"
	"log"
	"time"
)

func CreateTables(db *sql.DB) {
	createAccountTableQuery := `
        CREATE TABLE IF NOT EXISTS account (
            id SERIAL PRIMARY KEY,
            tg_id BIGINT UNIQUE,
            username TEXT,
            firstname TEXT,
            lastname TEXT
        );
    `
	_, err := db.Exec(createAccountTableQuery)
	if err != nil {
		log.Printf("Error creating account table: %v", err)
	}

	createAllDatesTableQuery := `
        CREATE TABLE IF NOT EXISTS all_dates (
            id SERIAL PRIMARY KEY,
            date_report DATE
        );
    `
	_, err = db.Exec(createAllDatesTableQuery)
	if err != nil {
		log.Printf("Error creating all_dates table: %v", err)
	}

	createSlotsTableQuery := `
        CREATE TABLE IF NOT EXISTS slots (
            id SERIAL PRIMARY KEY,
            time_interval VARCHAR(13) NOT NULL UNIQUE
        );
    `
	_, err = db.Exec(createSlotsTableQuery)
	if err != nil {
		log.Printf("Error creating slots table: %v", err)
	}

	createGroupProgramsTableQuery := `
    CREATE TABLE IF NOT EXISTS group_programs (
        id SERIAL PRIMARY KEY,
        program_name VARCHAR(255) NOT NULL UNIQUE
    );
`
	_, err = db.Exec(createGroupProgramsTableQuery)
	if err != nil {
		log.Printf("Error creating group_programs table: %v", err)
	}

	alterTableQuery := `
    ALTER TABLE group_programs
    ADD COLUMN IF NOT EXISTS capacity_limit INT NOT NULL DEFAULT 15;
`
	_, err = db.Exec(alterTableQuery)
	if err != nil {
		log.Printf("Error altering group_programs table: %v", err)
	}

	createScheduleTableQuery := `
        CREATE TABLE IF NOT EXISTS schedule (
    id SERIAL PRIMARY KEY,
    dt_id INTEGER NOT NULL,
    tm_id INTEGER NOT NULL,
    program_id INTEGER NOT NULL,
    UNIQUE (dt_id, tm_id, program_id),
    FOREIGN KEY (dt_id) REFERENCES all_dates (id),
    FOREIGN KEY (tm_id) REFERENCES slots (id),
    FOREIGN KEY (program_id) REFERENCES group_programs (id)
)`
	_, err = db.Exec(createScheduleTableQuery)
	if err != nil {
		log.Printf("Error creating schedule table: %v", err)
	}

	createusersRecordsTable := `
        CREATE TABLE users_records (
	id SERIAL PRIMARY KEY,
	first_name TEXT NOT NULL,
	last_name TEXT NOT NULL,
	date_report DATE NOT NULL,
	time_interval TEXT NOT NULL,
	program_name TEXT NOT NULL,
	UNIQUE (first_name, last_name, date_report, time_interval, program_name)
                                   )`
	_, err = db.Exec(createusersRecordsTable)
	if err != nil {
		log.Printf("Error creating schedule table: %v", err)
	}
	createAdministratorsTable := `
        CREATE TABLE administrators (
	id SERIAL PRIMARY KEY,
	user_id BIGINT UNIQUE NOT NULL
                                    )`
	_, err = db.Exec(createAdministratorsTable)
	if err != nil {
		log.Printf("Error creating schedule table: %v", err)
	}

}
func FillTables(db *sql.DB) {
	currentDate := time.Now()
	endOfYear := time.Date(currentDate.Year(), 12, 31, 0, 0, 0, 0, time.UTC)
	fmt.Print(endOfYear)

	for d := currentDate; d.Before(endOfYear) || d.Equal(endOfYear); d = d.AddDate(0, 0, 1) {
		_, err := db.Exec("INSERT INTO all_dates (date_report) SELECT $1 WHERE NOT EXISTS (SELECT 1 FROM all_dates WHERE date_report = $1)", d)
		if err != nil {
			log.Printf("Error inserting date %v: %v", d, err)
		}
	}

	/*
		for hour := 0; hour < 24; hour++ {
			timeInterval := fmt.Sprintf("%02d:00 - %02d:00", hour, (hour+1)%24)
			_, err := db.Exec("INSERT INTO slots (time_interval) VALUES ($1)", timeInterval)
			if err != nil {
				log.Printf("Error inserting time interval %s: %v", timeInterval, err)
			}
		}
		programs := []string{"Pilates", "Yoga", "Pole Dance"}
		for _, program := range programs {
			_, err := db.Exec("INSERT INTO group_programs (program_name) VALUES ($1)", program)
			if err != nil {
				log.Printf("Error inserting program %s: %v", program, err)
			}
		}

			programs := map[string]int{
				"Pilates":    15,
				"Yoga":       10,
				"Pole Dance": 5,
			}

			for program, limit := range programs {
				_, err := db.Exec("INSERT INTO group_programs (program_name, capacity_limit) VALUES ($1, $2)", program, limit)
				if err != nil {
					log.Printf("Error inserting program %s: %v", program, err)
				}
			}

			scheduleItems := []struct {
				date    string
				time    string
				program string
			}{
				{currentDate.Format("2006-01-02"), "13:00 - 14:00", "Yoga"},
				{currentDate.Format("2006-01-02"), "17:00 - 18:00", "Pilates"},
				{currentDate.Format("2006-01-02"), "22:00 - 23:00", "Pole Dance"},
			}

			var err error
			for _, item := range scheduleItems {
				var dtID, tmID, programID int
				err = db.QueryRow("SELECT id FROM all_dates WHERE date_report = $1", item.date).Scan(&dtID)
				if err != nil {
					log.Printf("Error getting date id for %s: %v", item.date, err)
					continue
				}
				err = db.QueryRow("SELECT id FROM slots WHERE time_interval = $1", item.time).Scan(&tmID)
				if err != nil {
					log.Printf("Error getting time interval id for %s: %v", item.time, err)
					continue
				}
				err = db.QueryRow("SELECT id FROM group_programs WHERE program_name = $1", item.program).Scan(&programID)
				if err != nil {
					log.Printf("Error getting program id for %s: %v", item.program, err)
					continue
				}

				_, err = db.Exec("INSERT INTO schedule (dt_id, tm_id, program_id) VALUES ($1, $2, $3)", dtID, tmID, programID)
				if err != nil {
					log.Printf("Error inserting schedule item (%s, %s, %s): %v", item.date, item.time, item.program, err)
				}
			}
	*/
}
