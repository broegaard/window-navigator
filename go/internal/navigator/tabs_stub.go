//go:build !windows

package navigator

func init() {
	DefaultTabFetcher = func(_ uintptr) []TabInfo { return nil }
	DefaultTabSelector = func(_ TabInfo) {}
}
