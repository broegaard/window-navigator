package navigator

import "image"

// TrayIconSize is the width and height of the generated tray icon image.
const TrayIconSize = 64

// MakeTrayIcon returns a TrayIconSize×TrayIconSize RGBA image filled with the desktop color.
// desktopNumber 0 renders grey (unknown). Text rendering is done by the platform layer.
func MakeTrayIcon(desktopNumber int) *image.RGBA {
	var r, g, b uint8
	if desktopNumber > 0 {
		c := DesktopColors[(desktopNumber-1)%len(DesktopColors)]
		r, g, b = c[0], c[1], c[2]
	} else {
		r, g, b = 60, 60, 60
	}

	img := image.NewRGBA(image.Rect(0, 0, TrayIconSize, TrayIconSize))
	for y := 0; y < TrayIconSize; y++ {
		for x := 0; x < TrayIconSize; x++ {
			i := img.PixOffset(x, y)
			img.Pix[i] = r
			img.Pix[i+1] = g
			img.Pix[i+2] = b
			img.Pix[i+3] = 255
		}
	}
	return img
}

// TrayIconBackend is the platform-specific tray icon implementation.
type TrayIconBackend interface {
	// Start shows the tray icon with the given desktop number.
	// Runs the platform message loop; returns when Stop is called.
	Start(desktopNumber int)
	// Update changes the displayed desktop number.
	Update(desktopNumber int)
	// Stop removes the tray icon and causes Start to return.
	Stop()
}
