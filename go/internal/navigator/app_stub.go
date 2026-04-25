//go:build !windows

package navigator

// SetDpiAwareness is a no-op on non-Windows platforms.
func SetDpiAwareness() {}

// StartFlashMonitor is a no-op on non-Windows platforms.
func StartFlashMonitor(_ *NotificationSet) {}

// StartOverlayHotkeyListener is a no-op on non-Windows platforms.
func StartOverlayHotkeyListener(_ chan<- struct{}) {}

// StartMoveHotkeyListener is a no-op on non-Windows platforms.
func StartMoveHotkeyListener(_ chan<- moveCmd) {}

// RunApp is a no-op on non-Windows platforms.
func RunApp() {}
