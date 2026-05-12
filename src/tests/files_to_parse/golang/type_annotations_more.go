package ta

type Red struct{}
type Blue struct{}

// Two distinct named types on one parameter list (parity with multi-annotation lines).
func Pair(a Red, b Blue) int { return 0 }
