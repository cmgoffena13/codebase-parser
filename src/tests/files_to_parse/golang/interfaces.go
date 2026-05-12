package iface

type Reader interface {
	Read(p []byte) (int, error)
}

type Writer interface {
	Write(p []byte) (int, error)
}

type ReadWriter interface {
	Reader
	Writer
}

type File struct{}

func (f *File) Read(p []byte) (int, error) {
	return 0, nil
}

func (f *File) Write(p []byte) (int, error) {
	return 0, nil
}