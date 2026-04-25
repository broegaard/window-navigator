//go:build !windows

package navigator

// noopTrayIcon is a no-op TrayIconBackend for non-Windows platforms.
type noopTrayIcon struct{}

func (noopTrayIcon) Start(_ int) {}
func (noopTrayIcon) Update(_ int) {}
func (noopTrayIcon) Stop()        {}

// NewTrayIcon returns a no-op TrayIconBackend on non-Windows platforms.
func NewTrayIcon(_ func()) TrayIconBackend {
	return noopTrayIcon{}
}
