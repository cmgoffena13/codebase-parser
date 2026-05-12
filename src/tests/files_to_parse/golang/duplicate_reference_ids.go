package dup

func callee() {}

func f() {
	callee()
	callee()
}
