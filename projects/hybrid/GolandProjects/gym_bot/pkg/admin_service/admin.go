package admin_service

import (
	"database/sql"
	"example.com/gym_bot/pkg/models"
	"fmt"
	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api"
	"log"
	"time"
)

var programShortNames = map[string]string{
	"Настольный теннис":   "NT",
	"Самба":               "СА",
	"Капоэйра":            "КА",
	"Йога":                "ЙО",
	"Медитация":           "МД",
	"Пилатес":             "ПТ",
	"Стретчинг":           "СТ",
	"Телесная настройка":  "ТН",
	"Кунг-Фу для лидеров": "КФ",
}

func getRussianWeekday(t time.Time) string {
	days := [...]string{"Воскресенье", "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"}
	return days[t.Weekday()]
}

func IsAdmin(db *sql.DB, userID int64) (bool, error) {
	var count int
	query := `SELECT COUNT(*) FROM administrators WHERE user_id = $1`
	err := db.QueryRow(query, userID).Scan(&count)
	if err != nil {
		return false, err
	}
	return count > 0, nil
}

//-------------------------------------------------

func HandleAdminCommand(db *sql.DB, bot *tgbotapi.BotAPI, chatID int64) {
	adminDates, err := getAdminDates(db)
	if err != nil {
		log.Printf("Error getting admin dates: %v", err)
		return
	}

	if len(adminDates) == 0 {
		msg := tgbotapi.NewMessage(chatID, "Нет записей")
		bot.Send(msg)
		return
	}

	msg := tgbotapi.NewMessage(chatID, "Выберите день:")
	msg.ReplyMarkup = createAdminDatesMarkup(adminDates)
	bot.Send(msg)
}

func createAdminDatesMarkup(adminDates []time.Time) tgbotapi.InlineKeyboardMarkup {
	var rows [][]tgbotapi.InlineKeyboardButton

	for _, date := range adminDates {
		dateStr := date.Format("2006-01-02")
		weekday := getRussianWeekday(date)
		button := tgbotapi.NewInlineKeyboardButtonData(fmt.Sprintf("%s - %s", weekday, dateStr), "admin_date_"+dateStr)
		//button := tgbotapi.NewInlineKeyboardButtonData(dateStr, "admin_date_"+dateStr)
		rows = append(rows, []tgbotapi.InlineKeyboardButton{button})
	}

	return tgbotapi.NewInlineKeyboardMarkup(rows...)
}

func getAdminDates(db *sql.DB) ([]time.Time, error) {
	rows, err := db.Query(`
		SELECT DISTINCT ur.date_report
		FROM users_records ur
		ORDER BY ur.date_report
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var dates []time.Time
	for rows.Next() {
		var date time.Time
		err := rows.Scan(&date)
		if err != nil {
			return nil, err
		}
		dates = append(dates, date)
	}
	return dates, nil
}

// -------------------------------------------------
func HandleAdminDateSelectCommand(db *sql.DB, bot *tgbotapi.BotAPI, chatID int64, selectedDate string) {
	markup, err := createAdminTimeProgramMarkup(db, selectedDate)
	if err != nil {
		log.Printf("Error creating admin time program markup: %v", err)
		return
	}

	msg := tgbotapi.NewMessage(chatID, "Выберите программу:")
	msg.ReplyMarkup = markup
	bot.Send(msg)
}

func createAdminTimeProgramMarkup(db *sql.DB, selectedDate string) (tgbotapi.InlineKeyboardMarkup, error) {
	records, err := getAdminTimePrograms(db, selectedDate)
	if err != nil {
		return tgbotapi.InlineKeyboardMarkup{}, err
	}

	buttons := make([][]tgbotapi.InlineKeyboardButton, len(records))
	for i, record := range records {
		buttonText := fmt.Sprintf("%s - %s", record.TimeInterval, record.ProgramName)

		shortProgramName, ok := programShortNames[record.ProgramName]
		if !ok {
			log.Printf("No short name for program %s", record.ProgramName)
			continue
		}
		callbackData := fmt.Sprintf("admin_time_program:%s|%s|%s", selectedDate, record.TimeInterval, shortProgramName)

		if len(callbackData) > 64 {
			return tgbotapi.InlineKeyboardMarkup{}, fmt.Errorf("callback data too long: %s", callbackData)
		}
		buttons[i] = tgbotapi.NewInlineKeyboardRow(tgbotapi.NewInlineKeyboardButtonData(buttonText, callbackData))
		//buttons[i] = tgbotapi.NewInlineKeyboardRow(tgbotapi.NewInlineKeyboardButtonData(buttonText, "admin_time_program:"+selectedDate+"|"+record.TimeInterval+"|"+record.ProgramName))
	}
	return tgbotapi.NewInlineKeyboardMarkup(buttons...), nil
}

func getAdminTimePrograms(db *sql.DB, selectedDate string) ([]models.UserActiveRecord, error) {
	var records []models.UserActiveRecord
	query := `
        SELECT DISTINCT time_interval, program_name
        FROM users_records
        WHERE date_report = $1
        ORDER BY time_interval, program_name`
	rows, err := db.Query(query, selectedDate)
	if err != nil {
		return nil, err
	}
	defer func(rows *sql.Rows) {
		err := rows.Close()
		if err != nil {

		}
	}(rows)

	for rows.Next() {
		record := models.UserActiveRecord{}
		err := rows.Scan(&record.TimeInterval, &record.ProgramName)
		if err != nil {
			return nil, err
		}
		records = append(records, record)
	}
	return records, nil
}

// -------------------------------------------------
/*
func HandleAdminTimeProgramSelectCommand(db *sql.DB, bot *tgbotapi.BotAPI, chatID int64, selectedDate, timeInterval, programName string) {
	users, err := getUsersByProgramAndDate(db, selectedDate, timeInterval, programName)
	if err != nil {
		log.Printf("Error getting users by program and date: %v", err)
		return
	}

	msgText := "Список участников:\n"
	for _, user := range users {
		msgText += fmt.Sprintf("- %s %s\n", user.FirstName, user.LastName)
	}

	msg := tgbotapi.NewMessage(chatID, msgText)
	bot.Send(msg)
}

*/

func HandleAdminTimeProgramSelectCommand(db *sql.DB, bot *tgbotapi.BotAPI, chatID int64, selectedDate, timeInterval, shortProgramName string) {
	// Декодирование сокращенного имени программы обратно в полное имя
	var programName string
	for k, v := range programShortNames {
		if v == shortProgramName {
			programName = k
			break
		}
	}

	// Замените все использования shortProgramName на programName ниже
	users, err := getUsersByProgramAndDate(db, selectedDate, timeInterval, programName)
	if err != nil {
		log.Printf("Error getting users by program and date: %v", err)
		return
	}

	msgText := "Список участников:\n"
	for _, user := range users {
		msgText += fmt.Sprintf("- %s %s\n", user.FirstName, user.LastName)
	}

	msg := tgbotapi.NewMessage(chatID, msgText)
	bot.Send(msg)
}

func getUsersByProgramAndDate(db *sql.DB, selectedDate, timeInterval, programName string) ([]tgbotapi.User, error) {
	users := []tgbotapi.User{}
	query := `
        SELECT first_name, last_name
        FROM users_records
        WHERE date_report = $1 AND time_interval = $2 AND program_name = $3
        ORDER BY first_name, last_name`
	rows, err := db.Query(query, selectedDate, timeInterval, programName)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	for rows.Next() {
		user := tgbotapi.User{}
		err := rows.Scan(&user.FirstName, &user.LastName)
		if err != nil {
			return nil, err
		}
		users = append(users, user)
	}
	return users, nil
}
