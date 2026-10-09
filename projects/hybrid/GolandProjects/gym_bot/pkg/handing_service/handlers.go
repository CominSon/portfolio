package handing_service

import (
	"database/sql"
	"example.com/gym_bot/pkg/admin_service"
	"example.com/gym_bot/pkg/models"
	"example.com/gym_bot/pkg/users_info_service"
	"fmt"
	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api"
	"log"
	"strings"
	"time"
)

var selectedDates = make(map[int64]string)
var userStates = make(map[int64]*models.UserState)

func getRussianWeekdayNew(t time.Time) string {
	days := [...]string{"воскресенье", "понедельник", "вторник", "среду", "четверг", "пятницу", "субботу"}
	return days[t.Weekday()]
}

func HandleUpdates(db *sql.DB, bot *tgbotapi.BotAPI, update *tgbotapi.Update) {
	if update.Message != nil && update.Message.IsCommand() {
		handleCommand(db, bot, update.Message.From, update.Message.Command())
	} else if update.Message != nil {
		chatID := update.Message.Chat.ID
		if userState, ok := userStates[chatID]; ok {
			switch userState.State {
			case "enter_first_name":
				userState.FirstName = update.Message.Text
				userState.State = "enter_last_name"

				msg := tgbotapi.NewMessage(chatID, "Введите вашу фамилию:")
				_, err := bot.Send(msg)
				if err != nil {
					log.Printf("Error sending message: %v", err)
				}
			case "enter_last_name":
				userState.LastName = update.Message.Text

				newUser := &tgbotapi.User{
					ID:        update.Message.From.ID,
					UserName:  update.Message.From.UserName,
					FirstName: userState.FirstName,
					LastName:  userState.LastName,
				}
				err := addUser(db, newUser, userState)
				if err != nil {
					log.Printf("Error adding user: %v", err)
					return
				}

				delete(userStates, chatID)

				msg := tgbotapi.NewMessage(chatID, "Спасибо за регистрацию!")
				_, err = bot.Send(msg)
				if err != nil {
					log.Printf("Error sending message: %v", err)
				}

				handleMenuCommand(db, bot, update.Message.From)
			}
		}
	} else if update.CallbackQuery != nil {
		chatID := update.CallbackQuery.Message.Chat.ID
		userID := update.CallbackQuery.From.ID
		userInfo, err := getUserInfo(db, int64(userID))
		if err != nil {
			log.Printf("Error getting user info: %v", err)
			return
		}
		switch update.CallbackQuery.Data {
		case "schedule":
			handleScheduleCommand(db, bot, chatID)
		case "my_records":
			users_info_service.HandleMyRecordsCommand(db, bot, chatID, userInfo.FirstName, userInfo.LastName)
		case "admin":
			admin_service.HandleAdminCommand(db, bot, chatID)
		default:
			// Если выбрана дата, обрабатываем ее
			if strings.HasPrefix(update.CallbackQuery.Data, "date:") {
				selectedDate := strings.TrimPrefix(update.CallbackQuery.Data, "date:")
				selectedDates[chatID] = selectedDate
				markup, err := createTimeProgramSelectionMarkup(db, selectedDate)
				if err != nil {
					log.Printf("Error creating time program selection markup: %v", err)
					return
				}

				msg := tgbotapi.NewMessage(chatID, "Выберите время занятий:")
				msg.ReplyMarkup = markup
				bot.Send(msg)
			}
			if strings.HasPrefix(update.CallbackQuery.Data, "time_program|") {
				data := strings.TrimPrefix(update.CallbackQuery.Data, "time_program|")
				parts := strings.Split(data, "|")
				timeInterval := parts[0]
				programName := parts[1]

				selectedDate := selectedDates[chatID]
				alreadyRegistered, err := users_info_service.IsUserAlreadyRegistered(db, userInfo.FirstName, userInfo.LastName, selectedDate, timeInterval, programName)
				if err != nil {
					log.Printf("Error checking user registration: %v", err)
					return
				}

				if alreadyRegistered {
					msg := tgbotapi.NewMessage(chatID, "Вы уже записались на эту программу")
					bot.Send(msg)
					handleCommand(db, bot, update.CallbackQuery.From, "menu")
				} else {
					err := users_info_service.RegisterUser(db, userInfo.FirstName, userInfo.LastName, selectedDate, timeInterval, programName)
					if err != nil {
						log.Printf("Error registering user: %v", err)
						return
					}

					parsedDate, _ := time.Parse(time.RFC3339, selectedDate)
					weekday := getRussianWeekdayNew(parsedDate)
					formattedDate := parsedDate.Format("02.01.2006")
					msg := tgbotapi.NewMessage(chatID, fmt.Sprintf("Вы успешно записались на %s - %s в период %s для программы %s", weekday, formattedDate, timeInterval, programName))
					///msg := tgbotapi.NewMessage(chatID, fmt.Sprintf("Вы успешно записались на %s в период %s для программы %s", formattedDate, timeInterval, programName))
					bot.Send(msg)
					handleCommand(db, bot, update.CallbackQuery.From, "menu")

				}
			}
			if strings.HasPrefix(update.CallbackQuery.Data, "record_id:") {
				recordID := strings.TrimPrefix(update.CallbackQuery.Data, "record_id:")
				users_info_service.HandleRecordDeletionConfirmation(db, bot, chatID, recordID)
			}
			if strings.HasPrefix(update.CallbackQuery.Data, "delete_record_yes|") {
				recordID := strings.TrimPrefix(update.CallbackQuery.Data, "delete_record_yes|")
				users_info_service.DeleteUserRecord(db, bot, chatID, userInfo.FirstName, userInfo.LastName, recordID)
				handleCommand(db, bot, update.CallbackQuery.From, "menu")
			} else if strings.HasPrefix(update.CallbackQuery.Data, "delete_record_no|") {
				handleCommand(db, bot, update.CallbackQuery.From, "menu")
			}
			if strings.HasPrefix(update.CallbackQuery.Data, "admin_date_") {
				selectedDate := strings.TrimPrefix(update.CallbackQuery.Data, "admin_date_")
				admin_service.HandleAdminDateSelectCommand(db, bot, chatID, selectedDate)
			}
			if strings.HasPrefix(update.CallbackQuery.Data, "admin_time_program:") {
				data := strings.TrimPrefix(update.CallbackQuery.Data, "admin_time_program:")
				parts := strings.Split(data, "|")
				selectedDate := parts[0]
				timeInterval := parts[1]
				programName := parts[2]

				admin_service.HandleAdminTimeProgramSelectCommand(db, bot, chatID, selectedDate, timeInterval, programName)
			}

		}
	}
}
