package main

type Container[T any] struct {
	Value T
}

func NewContainer[T any]() *Container[T] {
	return &Container[T]{}
}

func main() {
	c := NewContainer[string]()
	c.Value = "test"
	_ = Container[string]{Value: "x"}
}
