//go:build !windows

package navigator

type noopOverlay struct{}

func (noopOverlay) Show([]WindowInfo, int) {}
func (noopOverlay) Hide()                  {}

// NewOverlay returns a no-op overlay on non-Windows platforms.
func NewOverlay(_ OverlayCallbacks) Overlay { return noopOverlay{} }
