package navigator

// OverlayCallbacks contains the callbacks the overlay invokes when the user makes a selection.
type OverlayCallbacks struct {
	OnActivate func(hwnd uintptr) // focus the window (no move)
	OnMove     func(hwnd uintptr) // move to current desktop then focus
}

// Overlay is the floating window-picker UI.
type Overlay interface {
	Show(windows []WindowInfo, initialDesktop int)
	Hide()
}
