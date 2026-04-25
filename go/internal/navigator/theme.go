package navigator

import "fmt"

// DesktopColors is the shared palette for virtual desktop badges and the tray icon.
// Index 0 = desktop 1, cycling when desktop number exceeds the slice length.
var DesktopColors = [][3]uint8{
	{0, 60, 150},   // blue
	{160, 50, 0},   // orange
	{0, 120, 60},   // green
	{120, 0, 120},  // purple
	{160, 0, 40},   // red
	{0, 110, 120},  // teal
	{100, 80, 0},   // amber
	{60, 60, 60},   // grey
}

// DesktopBadgeColor returns a CSS hex color string (e.g. "#003c96") for the given
// 1-based desktop number, cycling through DesktopColors.
func DesktopBadgeColor(desktopNumber int) string {
	c := DesktopColors[(desktopNumber-1)%len(DesktopColors)]
	return fmt.Sprintf("#%02x%02x%02x", c[0], c[1], c[2])
}
