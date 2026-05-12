package refs

import "os"

var ConfigPath = "/etc/app.conf"

const MaxRetries = 3

func LoadConfig() (string, error) {
	data, err := os.ReadFile(ConfigPath)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

type App struct {
	Name   string
	Config string
}

func (a *App) Run() {
	cfg, _ := LoadConfig()
	a.Config = cfg
}