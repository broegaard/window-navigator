//go:build !windows

package navigator

func InitDebugLog()                     {}
func DbgLog(_ string, _ ...any) {}
