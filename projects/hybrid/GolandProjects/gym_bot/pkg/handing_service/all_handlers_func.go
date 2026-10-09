package handing_service

import (
	"database/sql"
	"example.com/gym_bot/pkg/admin_service"
	"example.com/gym_bot/pkg/models"
	"fmt"
	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api"
	"log"
	"time"
)

//---------------------------------

func addUser(db *sql.DB, user *tgbotapi.User, userState *models.UserState) error {
	_, err := db.Exec(`
        INSERT INTO account (tg_id, username, firstname, lastname) VALUES ($1, $2, $3, $4)
        ON CONFLICT (tg_id) DO UPDATE SET username = $2, firstname = $3, lastname = $4
    `, user.ID, user.UserName, userState.FirstName, userState.LastName)
	return err
}

func getUserInfo(db *sql.DB, userID int64) (*models.UserState, error) {
	var userState models.UserState
	err := db.QueryRow(`
		SELECT tg_id, firstname, lastname FROM account WHERE tg_id = $1
	`, userID).Scan(&userState.ChatID, &userState.FirstName, &userState.LastName)

	if err != nil {
		return nil, err
	}

	return &userState, nil
}
func getRussianWeekday(t time.Time) string {
	days := [...]string{"Воскресенье", "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"}
	return days[t.Weekday()]
}

/*
	func createTimeProgramSelectionMarkup(db *sql.DB, selectedDate string) (tgbotapi.InlineKeyboardMarkup, error) {
		rows, err := db.Query(`
			SELECT sl.time_interval, gp.program_name
				FROM schedule s
				JOIN slots sl ON s.tm_id = sl.id
				JOIN group_programs gp ON s.program_id = gp.id
				JOIN all_dates ad ON s.dt_id = ad.id
				WHERE ad.date_report = $1 AND (
					SELECT COUNT(*)
					FROM users_records
					WHERE date_report = ad.date_report AND time_interval = sl.time_interval AND program_name = gp.program_name
				) < 15
				ORDER BY sl.time_interval
		`, selectedDate)
		if err != nil {
			return tgbotapi.InlineKeyboardMarkup{}, err
		}
		defer rows.Close()

		var buttons [][]tgbotapi.InlineKeyboardButton
		for rows.Next() {
			var timeInterval, programName string
			err = rows.Scan(&timeInterval, &programName)
			if err != nil {
				return tgbotapi.InlineKeyboardMarkup{}, err
			}

			callbackData := fmt.Sprintf("time_program|%s|%s", timeInterval, programName)
			button := tgbotapi.NewInlineKeyboardButtonData(fmt.Sprintf("%s - %s", timeInterval, programName), callbackData)
			buttons = append(buttons, tgbotapi.NewInlineKeyboardRow(button))
		}

		markup := tgbotapi.NewInlineKeyboardMarkup(buttons...)
		return markup, nil
	}
*/
func createTimeProgramSelectionMarkup(db *sql.DB, selectedDate string) (tgbotapi.InlineKeyboardMarkup, error) {
	rows, err := db.Query(`
		SELECT sl.time_interval, gp.program_name
			FROM schedule s
			JOIN slots sl ON s.tm_id = sl.id
			JOIN group_programs gp ON s.program_id = gp.id
			JOIN all_dates ad ON s.dt_id = ad.id
			WHERE ad.date_report = $1 AND (
				SELECT COUNT(*)
				FROM users_records
				WHERE date_report = ad.date_report AND time_interval = sl.time_interval AND program_name = gp.program_name
			) < gp.capacity_limit
			ORDER BY sl.time_interval
	`, selectedDate)
	if err != nil {
		return tgbotapi.InlineKeyboardMarkup{}, err
	}
	defer rows.Close()

	var buttons [][]tgbotapi.InlineKeyboardButton
	for rows.Next() {
		var timeInterval, programName string
		err = rows.Scan(&timeInterval, &programName)
		if err != nil {
			return tgbotapi.InlineKeyboardMarkup{}, err
		}

		callbackData := fmt.Sprintf("time_program|%s|%s", timeInterval, programName)
		button := tgbotapi.NewInlineKeyboardButtonData(fmt.Sprintf("%s - %s", timeInterval, programName), callbackData)
		buttons = append(buttons, tgbotapi.NewInlineKeyboardRow(button))
	}

	markup := tgbotapi.NewInlineKeyboardMarkup(buttons...)
	return markup, nil
}

//---------------------------------

func handleCommand(db *sql.DB, bot *tgbotapi.BotAPI, user *tgbotapi.User, command string) {
	switch command {
	case "start":
		handleStartCommand(db, bot, user)
	case "menu":
		handleMenuCommand(db, bot, user)
	case "schedule":
		chatID := int64(user.ID)
		handleScheduleCommand(db, bot, chatID)
	}
}

// ----------------------------------------------------------------
func handleStartCommand(db *sql.DB, bot *tgbotapi.BotAPI, user *tgbotapi.User) {
	chatID := int64(user.ID)
	exists, err := checkUserExists(db, int64(user.ID))
	if err != nil {
		log.Printf("Error checking user existence: %v", err)
		return
	}

	if exists {
		handleMenuCommand(db, bot, user)
	} else {
		msg := tgbotapi.NewMessage(chatID, "Приветствую! Прошу заполните форму регистрации!")
		_, err := bot.Send(msg)
		if err != nil {
			log.Printf("Error sending message: %v", err)
			return
		}

		// Устанавливаем состояние для пользователя
		userStates[chatID] = &models.UserState{
			ChatID: chatID,
			State:  "enter_first_name",
		}

		// Отправляем сообщение с просьбой ввести имя
		msg = tgbotapi.NewMessage(chatID, "Введите ваше имя:")
		_, err = bot.Send(msg)
		if err != nil {
			log.Printf("Error sending message: %v", err)
		}
	}
}

// ------------------------------------------------------------------------------------
func handleMenuCommand(db *sql.DB, bot *tgbotapi.BotAPI, user *tgbotapi.User) {
	chatID := int64(user.ID)

	// Проверка наличия пользователя в базе данных
	exists, err := checkUserExists(db, int64(user.ID))
	if err != nil {
		log.Printf("Error checking user existence: %v", err)
		return
	}

	if !exists {
		msg := tgbotapi.NewMessage(chatID, "Вы не зарегистрированы.")
		bot.Send(msg)
		handleStartCommand(db, bot, user)
		return
	}

	userInfo, err := getUserInfo(db, int64(user.ID))
	if err != nil {
		log.Printf("Error getting user info: %v", err)
		return
	}

	msg := tgbotapi.NewMessage(chatID, fmt.Sprintf("Привет, %s!", userInfo.FirstName))
	bot.Send(msg)

	hasRecords, err := hasUserRecords(db, userInfo.FirstName, userInfo.LastName)
	if err != nil {
		log.Printf("Error checking user records: %v", err)
		return
	}
	msg = tgbotapi.NewMessage(chatID, "Выберите действие:")
	markup, err := createWelcomeMarkup(db, int64(user.ID), hasRecords)
	if err != nil {
		log.Printf("Error creating welcome markup: %v", err)
		return
	}
	msg.ReplyMarkup = markup
	bot.Send(msg)
}

func checkUserExists(db *sql.DB, userID int64) (bool, error) {
	var count int
	err := db.QueryRow("SELECT COUNT(*) FROM account WHERE tg_id = $1", userID).Scan(&count)
	if err != nil {
		return false, err
	}
	return count > 0, nil
}

func handleScheduleCommand(db *sql.DB, bot *tgbotapi.BotAPI, chatID int64) {
	msg := tgbotapi.NewMessage(chatID, "Выберите дату:")
	msg.ReplyMarkup, _ = createDateSelectionMarkup(db)
	bot.Send(msg)
}

func createDateSelectionMarkup(db *sql.DB) (*tgbotapi.InlineKeyboardMarkup, error) {
	today := time.Now().Format("2006-01-02")
	twoWeeksLater := time.Now().AddDate(0, 0, 14).Format("2006-01-02")
	rows, err := db.Query(`
		SELECT DISTINCT d.date_report
		FROM all_dates d
		JOIN schedule sch ON sch.dt_id = d.id
		WHERE d.date_report >= $1 AND d.date_report <= $2
		ORDER BY d.date_report
	`, today, twoWeeksLater)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var buttons [][]tgbotapi.InlineKeyboardButton
	for rows.Next() {
		var date string
		err := rows.Scan(&date)
		if err != nil {
			return nil, err
		}

		parsedDate, _ := time.Parse(time.RFC3339, date)
		formattedDate := parsedDate.Format("02.01.2006")
		weekday := getRussianWeekday(parsedDate)
		button := tgbotapi.NewInlineKeyboardButtonData(fmt.Sprintf("%s - %s", weekday, formattedDate), "date:"+date)
		//button := tgbotapi.NewInlineKeyboardButtonData(formattedDate, "date:"+date)

		buttons = append(buttons, []tgbotapi.InlineKeyboardButton{button})
	}

	markup := tgbotapi.NewInlineKeyboardMarkup(buttons...)
	return &markup, nil
}

func hasUserRecords(db *sql.DB, firstName, lastName string) (bool, error) {
	today := time.Now().Format("2006-01-02")
	var count int
	err := db.QueryRow(`SELECT COUNT(*) FROM users_records WHERE first_name = $1 AND last_name = $2 AND date_report >= $3`, firstName, lastName, today).Scan(&count)
	if err != nil {
		return false, err
	}
	return count > 0, nil
}

func createWelcomeMarkup(db *sql.DB, userID int64, hasRecords bool) (tgbotapi.InlineKeyboardMarkup, error) {
	var buttons []tgbotapi.InlineKeyboardButton
	scheduleBtn := tgbotapi.NewInlineKeyboardButtonData("Расписание", "schedule")
	buttons = append(buttons, scheduleBtn)

	if hasRecords {
		myRecordsBtn := tgbotapi.NewInlineKeyboardButtonData("Мои записи", "my_records")
		buttons = append(buttons, myRecordsBtn)
	}

	isAdmin, err := admin_service.IsAdmin(db, userID)
	if err != nil {
		return tgbotapi.InlineKeyboardMarkup{}, err
	}

	if isAdmin {
		adminBtn := tgbotapi.NewInlineKeyboardButtonData("Администрирование", "admin")
		buttons = append(buttons, adminBtn)
	}

	return tgbotapi.NewInlineKeyboardMarkup(buttons), nil
}
