package navigator

// WindowInfo represents a single open window.
type WindowInfo struct {
	HWND             uintptr
	Title            string
	ProcessName      string
	DesktopNumber    int  // 1-based; 0 = unknown
	IsCurrentDesktop bool // false if on a different virtual desktop
	HasNotification  bool
	// Icon is intentionally omitted here; the UI layer owns image data.
}

// TabInfo represents a single browser/app tab within a parent window.
type TabInfo struct {
	Name  string
	HWND  uintptr // parent window HWND
	Index int     // 0-based position in parent's tab list; used to re-fetch on select
}
