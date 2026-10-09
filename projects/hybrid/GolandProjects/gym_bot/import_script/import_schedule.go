package import_script

import (
	"database/sql"
	"fmt"
	"github.com/tealeg/xlsx"
	"time"
)

func LoadAllDates(db *sql.DB) (map[string]int, error) {
	rows, err := db.Query("SELECT id, date_report FROM all_dates")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	allDates := make(map[string]int)
	for rows.Next() {
		var id int
		var dateReport time.Time
		err := rows.Scan(&id, &dateReport)
		if err != nil {
			return nil, err
		}
		allDates[dateReport.Format("02.01.2006")] = id
	}
	return allDates, nil
}

func LoadSlots(db *sql.DB) (map[string]int, error) {
	rows, err := db.Query("SELECT id, time_interval FROM slots")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	slots := make(map[string]int)
	for rows.Next() {
		var id int
		var timeInterval string
		err := rows.Scan(&id, &timeInterval)
		if err != nil {
			return nil, err
		}
		slots[timeInterval] = id
	}
	return slots, nil
}

func LoadProgramNames(db *sql.DB) (map[string]int, error) {
	rows, err := db.Query("SELECT id, program_name FROM group_programs")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	programNames := make(map[string]int)
	for rows.Next() {
		var id int
		var programName string
		err := rows.Scan(&id, &programName)
		if err != nil {
			return nil, err
		}
		programNames[programName] = id
	}
	return programNames, nil
}

func ImportSchedule(db *sql.DB, xlFile *xlsx.File, allDates, slots, programNames map[string]int) error {
	tx, err := db.Begin()
	if err != nil {
		return fmt.Errorf("failed to start transaction: %v", err)
	}

	defer func() {
		if r := recover(); r != nil {
			tx.Rollback()
			err = fmt.Errorf("failed to import schedule: %v", r)
		}
	}()
	stmt, err := tx.Prepare(`INSERT INTO schedule (dt_id, tm_id, program_id) VALUES ($1, $2, $3) ON CONFLICT (dt_id, tm_id, program_id) DO NOTHING`)
	if err != nil {
		return fmt.Errorf("failed to prepare insert statement: %v", err)
	}
	/*
		stmt, err := tx.Prepare(`INSERT INTO schedule (dt_id, tm_id, program_id) VALUES ($1, $2, $3)`)
		if err != nil {
			return fmt.Errorf("failed to prepare insert statement: %v", err)
		}
	*/

	defer stmt.Close()

	for _, sheet := range xlFile.Sheets {
		for i, row := range sheet.Rows {
			if i == 0 {
				continue
			}

			if len(row.Cells) < 3 {
				continue
			}

			dateReportsStr, timeIntervalStr, programNameStr := row.Cells[0].String(), row.Cells[1].String(), row.Cells[2].String()
			if dateReportsStr == "" || timeIntervalStr == "" || programNameStr == "" {
				continue
			}

			dateReports, err := time.Parse("01-02-06", dateReportsStr)

			if err != nil {
				return fmt.Errorf("failed to parse date_reports: %v", err)
			}
			dateReportsStr = dateReports.Format("02.01.2006")
			dtID, ok := allDates[dateReportsStr]

			if !ok {
				return fmt.Errorf("unknown date_reports: %s", dateReportsStr)
			}

			tmID, ok := slots[timeIntervalStr]
			if !ok {
				return fmt.Errorf("unknown time_interval: %s", timeIntervalStr)
			}

			programID, ok := programNames[programNameStr]
			if !ok {
				return fmt.Errorf("unknown program_name: %s", programNameStr)
			}

			_, err = stmt.Exec(dtID, tmID, programID)
			if err != nil {
				return fmt.Errorf("failed to insert schedule entry: %v", err)
			}
		}
	}

	err = tx.Commit()
	if err != nil {
		return fmt.Errorf("failed to commit transaction: %v", err)
	}

	return nil
}
