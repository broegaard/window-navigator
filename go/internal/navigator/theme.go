package navigator

import "fmt"

// DesktopColors is the shared palette for virtual desktop badges and the tray icon.
// Index 0 = desktop 1, cycling when desktop number exceeds the slice length.
var DesktopColors = [][3]uint8{
	{160, 45, 15},  // vermilion   hue~15°
	{135, 100, 0},  // dark amber  hue~55°
	{55, 95, 0},    // dark lime   hue~100°
	{0, 115, 80},   // dark jade   hue~145°
	{0, 100, 120},  // ocean teal  hue~190°
	{25, 65, 160},  // cobalt blue hue~230°
	{80, 0, 155},   // deep violet hue~270°
	{145, 0, 115},  // dark rose   hue~315°
}

// DesktopBadgeColor returns a CSS hex color string (e.g. "#003c96") for the given
// 1-based desktop number, cycling through DesktopColors.
func DesktopBadgeColor(desktopNumber int) string {
	c := DesktopColors[(desktopNumber-1)%len(DesktopColors)]
	return fmt.Sprintf("#%02x%02x%02x", c[0], c[1], c[2])
}
