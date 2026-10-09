package main

import (
	"example.com/gym_bot/pkg/database_service"
	"example.com/gym_bot/pkg/handing_service"
	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api"
	_ "github.com/lib/pq"
	"log"
	"os"
)

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	botToken := os.Getenv("BOT_TOKEN")
	if botToken == "" {
		log.Fatal("BOT_TOKEN must be set")
	}

	bot, err := tgbotapi.NewBotAPI(botToken)
	if err != nil {
		log.Fatal(err)
	}

	db, _ := database_service.InitDatabaseConnection()
	defer db.Close()

	database_service.CreateTables(db)
	database_service.FillTables(db)

	bot.Debug = false

	log.Printf("Logged in to the account %s", bot.Self.UserName)

	u := tgbotapi.NewUpdate(0)
	u.Timeout = 60

	updates, err := bot.GetUpdatesChan(u)

	for update := range updates {
		handing_service.HandleUpdates(db, bot, &update)
	}
}
