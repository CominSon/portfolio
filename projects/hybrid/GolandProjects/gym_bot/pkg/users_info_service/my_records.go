package users_info_service

import (
	"database/sql"
	"example.com/gym_bot/pkg/models"
	"fmt"
	"log"
	"time"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api"
)

func getRussianWeekday(t time.Time) string {
	days := [...]string{"Воскресенье", "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"}
	return days[t.Weekday()]
}

func getActiveUserRecords(db *sql.DB, firstName, lastName string) ([]models.UserActiveRecord, error) {
	var records []models.UserActiveRecord
	today := time.Now().Format("2006-01-02")
	query := `
        SELECT id, date_report, time_interval, program_name 
        FROM users_records
        WHERE first_name = $1 AND last_name = $2 AND date_report >= $3
        ORDER BY date_report, time_interval`
	rows, err := db.Query(query, firstName, lastName, today)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	for rows.Next() {
		record := models.UserActiveRecord{}
		err := rows.Scan(&record.ID, &record.DateReport, &record.TimeInterval, &record.ProgramName)
		if err != nil {
			return nil, err
		}
		records = append(records, record)
	}
	return records, nil
}

func createMyRecordsMarkup(records []models.UserActiveRecord) (tgbotapi.InlineKeyboardMarkup, error) {
	buttons := make([][]tgbotapi.InlineKeyboardButton, len(records))
	for i, record := range records {
		parsedDate, _ := time.Parse(time.RFC3339, record.DateReport)
		formattedDate := parsedDate.Format("2006-01-02")
		weekday := getRussianWeekday(parsedDate)
		buttonText := fmt.Sprintf("%s - %s | %s | %s", weekday, formattedDate, record.TimeInterval, record.ProgramName)
		//buttonText := fmt.Sprintf("%s | %s - %s", formattedDate, record.TimeInterval, record.ProgramName)
		callbackData := fmt.Sprintf("record_id:%s", record.ID)
		buttons[i] = tgbotapi.NewInlineKeyboardRow(tgbotapi.NewInlineKeyboardButtonData(buttonText, callbackData))
	}

	return tgbotapi.NewInlineKeyboardMarkup(buttons...), nil
}

func HandleMyRecordsCommand(db *sql.DB, bot *tgbotapi.BotAPI, chatID int64, firstName, lastName string) {
	userRecords, err := getActiveUserRecords(db, firstName, lastName)
	if err != nil {
		log.Printf("Error getting active user records: %v", err)
		return
	}

	if len(userRecords) == 0 {
		msg := tgbotapi.NewMessage(chatID, "У вас нет активных записей.")
		bot.Send(msg)
		return
	}
	msg := tgbotapi.NewMessage(chatID, "Выберите вашу активную запись, которую хотите удалить:")

	markup, err := createMyRecordsMarkup(userRecords)
	if err != nil {
		log.Printf("Error creating my records markup: %v", err)
		return
	}

	msg.ReplyMarkup = markup
	bot.Send(msg)
}

func HandleRecordDeletionConfirmation(db *sql.DB, bot *tgbotapi.BotAPI, chatID int64, recordID string) {
	msg := tgbotapi.NewMessage(chatID, "Вы хотите удалить эту запись?")
	markup := tgbotapi.NewInlineKeyboardMarkup(
		tgbotapi.NewInlineKeyboardRow(
			tgbotapi.NewInlineKeyboardButtonData("Да", "delete_record_yes|"+recordID),
			tgbotapi.NewInlineKeyboardButtonData("Нет", "delete_record_no|"+recordID),
		),
	)
	msg.ReplyMarkup = markup
	bot.Send(msg)
}
func DeleteUserRecord(db *sql.DB, bot *tgbotapi.BotAPI, chatID int64, firstName, lastName, recordID string) {
	_, err := db.Exec("DELETE FROM users_records WHERE id = $1 AND first_name = $2 AND last_name = $3", recordID, firstName, lastName)
	if err != nil {
		log.Printf("Error deleting user record: %v", err)
		return
	}
	msg := tgbotapi.NewMessage(chatID, "Ваша запись успешно удалена.")
	bot.Send(msg)
}

// RegisterUser ------------------------------
func RegisterUser(db *sql.DB, firstName, lastName, dateReport, timeInterval, programName string) error {
	_, err := db.Exec(`
		INSERT INTO users_records (first_name, last_name, date_report, time_interval, program_name)
		VALUES ($1, $2, $3, $4, $5)
	`, firstName, lastName, dateReport, timeInterval, programName)
	return err
}

func IsUserAlreadyRegistered(db *sql.DB, firstName, lastName, dateReport, timeInterval, programName string) (bool, error) {
	var count int
	err := db.QueryRow(`
		SELECT COUNT(*)
		FROM users_records
		WHERE first_name = $1 AND last_name = $2 AND date_report = $3 AND time_interval = $4 AND program_name = $5
	`, firstName, lastName, dateReport, timeInterval, programName).Scan(&count)

	if err != nil {
		return false, err
	}

	return count > 0, nil
}

// ---------------------------------------------
