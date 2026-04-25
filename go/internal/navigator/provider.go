package navigator

import "image"

// WindowFilter is a predicate applied to each candidate window after process name resolution.
// Return true to include the window, false to skip it.
type WindowFilter func(hwnd uintptr, title string, processName string) bool

// WindowProvider enumerates open windows.
type WindowProvider interface {
	GetWindows() []WindowInfo
}

// DesktopAssigner maps HWNDs to desktop numbers and current-desktop flags.
type DesktopAssigner func(hwnds []uintptr) (numbers map[uintptr]int, isCurrent map[uintptr]bool)

// IconSize is the fixed dimensions of extracted icons.
const IconSize = 32

// FallbackIcon returns a plain grey 32×32 RGBA image used when icon extraction fails.
func FallbackIcon() *image.RGBA {
	img := image.NewRGBA(image.Rect(0, 0, IconSize, IconSize))
	for i := range img.Pix {
		switch i % 4 {
		case 0, 1, 2:
			img.Pix[i] = 128
		case 3:
			img.Pix[i] = 255
		}
	}
	return img
}
