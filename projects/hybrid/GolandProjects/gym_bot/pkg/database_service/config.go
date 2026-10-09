package database_service

import (
	"example.com/gym_bot/pkg/models"
	"gopkg.in/yaml.v3"
	"log"
	"os"
)

func LoadConfig() (*models.Config, error) {
	config := &models.Config{}
	yamlFile, err := os.ReadFile("resources/application.yaml")
	if err != nil {
		log.Printf("Failed to read YAML file: %v", err)
		return nil, err
	}
	err = yaml.Unmarshal(yamlFile, config)
	if err != nil {
		log.Printf("Failed to unmarshal YAML: %v", err)
		return nil, err
	}
	return config, nil
}
