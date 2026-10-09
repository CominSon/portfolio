package database_service

import (
	"database/sql"
	"fmt"
	_ "github.com/lib/pq"
	"log"
)

func InitDatabaseConnection() (*sql.DB, error) {
	config, err := LoadConfig()
	if err != nil {
		log.Printf("Failed to load config: %v", err)
		return nil, err
	}

	dbConfig := config.Database
	connStr := fmt.Sprintf("host=%s port=%d user=%s password=%s dbname=%s sslmode=%s",
		dbConfig.Host, dbConfig.Port, dbConfig.User, dbConfig.Password, dbConfig.DBName, dbConfig.SSLMode)

	db, err := sql.Open("postgres", connStr)
	if err != nil {
		log.Printf("Failed to open database connection: %v", err)
		return nil, err
	}

	err = db.Ping()
	if err != nil {
		log.Printf("Failed to ping database: %v", err)
		return nil, err
	}
	CreateTables(db)
	//FillTables(db)

	return db, nil
}

func InitConnection() (*sql.DB, error) {
	config, err := LoadConfig()
	if err != nil {
		log.Printf("Failed to load config: %v", err)
		return nil, err
	}

	dbConfig := config.Database
	connStr := fmt.Sprintf("host=%s port=%d user=%s password=%s dbname=%s sslmode=%s",
		dbConfig.Host, dbConfig.Port, dbConfig.User, dbConfig.Password, dbConfig.DBName, dbConfig.SSLMode)

	db, err := sql.Open("postgres", connStr)
	if err != nil {
		log.Printf("Failed to open database connection: %v", err)
		return nil, err
	}

	err = db.Ping()
	if err != nil {
		log.Printf("Failed to ping database: %v", err)
		return nil, err
	}

	return db, nil
}
