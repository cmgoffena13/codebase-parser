package basic

import "fmt"
import "strings"

type Server struct {
	Name    string
	Port    int
	Handler *Handler
}

type Handler struct{}

func NewServer(name string) *Server {
	return &Server{Name: name}
}

func (s *Server) Start() error {
	fmt.Println(s.Name)
	return nil
}

func (s *Server) Handle(req string) string {
	return strings.TrimSpace(req)
}

func main() {
	srv := NewServer("test")
	srv.Start()
}